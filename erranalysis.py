#! /usr/bin/python
import argparse
import sys
import io
import datetime
from subprocess import Popen, call, PIPE

MOSES_WORKING_DIR = "moses-working-dir"
CORPORA_NAME = "corpora-name"
RUN_NUMBER = "run-number"
MOSES_BIN_DIR = "moses-bin-dir"
ANALYSIS_DIR = "analysis-dir"

argparser = argparse.ArgumentParser("A tool to make error analysis of Moses output easier")
argparser.add_argument("--kbest", "-k", action='store', type=int, help="the k-value for the generated k-best translation list")
argparser.add_argument("--distinct", "-d", action='store_true', default=False, help="whether only output distinct sentences in the k-best list")
argparser.add_argument("--inputFile", "-i", action='store', type=str, help="the input source file for the analysis (default value would be the evaluation input of specified moses-working-dir and run-number in the config file)")
argparser.add_argument("--sentenceid", "-s", action='store', type=int, required=True, help="identify the sentence id (line number) you want to analysis in the inputFile you identified")
argparser.add_argument("--outputFile", "-o", action='store', type=str, help="the output report for the analysis, specify \"-\" as this option for STDOUT")
argparser.add_argument("--refFile", "-r", action='store', nargs = '*', type=str, help="the reference files in the target language, must be specified when you want to do force decoding (default value would be the evaluation reference of the specified moses-working-dir and run in the config file)")
argparser.add_argument("--bleu", "-b", action='store_true', default=False, help="output bleu score for the translation output")
argparser.add_argument("--force", "-f", action='store_true', default=False, help="clamp the output as the final translation and do the decoding")
argparser.add_argument("--decodersettings", action='store', type=str, help="extra options for the decoder")
argparser.add_argument("--trace", "-t", action='store_true', default=False, help="output decoding trace for the translation output")

args = argparser.parse_args()

if __name__ == "__main__":
	if args.kbest and args.force:
		raise EnvironmentError("cannot generate k-best list and do force encoding at the same time.")
	if not args.refFile and args.force:
		raise EnvironmentError("cannot do force decoding without specifying refFile.")
	if not (args.refFile and len(args.refFile) == 1) and args.force:
		raise EnvironmentError("cannot do force decoding with more than one refFile.")

	# read cfg
	cfgfile = open('.cfg', 'r')
	cfgvar = {}
	for line in cfgfile:
		if not line.startswith("#"):
			toks = line.split('=')
			cfgvar[toks[0].strip()] = toks[1].strip()

	# prepare the directory
	now = datetime.datetime.now()
	dirname = cfgvar[ANALYSIS_DIR] + "/" + now.strftime("%S-%M-%H_%Y-%m-%d") + "/"
	call("mkdir " + dirname, shell=True)

	# prepare sentence input
	if args.inputFile:
		inputFile = open(inputFile, 'r')
	else:
		inputFile = open(cfgvar[MOSES_WORKING_DIR] + "/evaluation/" + cfgvar[CORPORA_NAME] + ".input.tc." + cfgvar[RUN_NUMBER], 'r')
	linen = 0
	for line in inputFile:
		if linen == args.sentenceid:
			inputSent = line.strip()
			break
		linen += 1
	else:
		raise IOError("sentenceid exceeded the length of input file")

	# prepare reference file
	if args.bleu or args.force:
		if args.kbest:
			k = args.kbest
		else:
			k = 1
		if args.refFile:
			origrefs = args.refFile
			defaultRef = False
		else:
			origrefs = [(cfgvar[MOSES_WORKING_DIR] + "/evaluation/" + refname.strip())\
					for refname in Popen("ls " +  cfgvar[MOSES_WORKING_DIR] + "/evaluation/ | grep \'" + cfgvar[CORPORA_NAME] + ".reference.tok.*.ref*\'", shell=True, stdout=PIPE)\
					.stdout.read().split('\n')]
			origrefs.pop()
			defaultRef = True
		refs = [(dirname + "tmp.ref" + str(i)) for i in range(0, len(origrefs))]
		# find correct reference and copy k times
		for (origref, ref) in zip(origrefs, refs):
			linen = 0
			origrefFile = open(origref, 'r')
			for line in origrefFile:
				if (not defaultRef) or linen == args.sentenceid:
					refFile = open(ref, 'w')
					for kk in range(0, k):
						refFile.write(line)
					refFile.close()
					break
				linen += 1
			origrefFile.close()

	# prepare ini
	origini = cfgvar[MOSES_WORKING_DIR] + "/evaluation/" + cfgvar[CORPORA_NAME] + ".filtered.ini." + cfgvar[RUN_NUMBER]
	ini = dirname + "moses.ini"
	if args.force:
		print origini
		originiFile = open(origini, 'r')
		iniFile = open(ini, 'w')
		isFeature = False
		for line in originiFile:
			if line.strip() == "[feature]":
				isFeature = True
			if isFeature and line.strip() == "":
				iniFile.write("ConstrainedDecoding path=" + refs[0] + "\n")
				isFeature = False
			iniFile.write(line)
		iniFile.close()
		originiFile.close()
	else:
		call("cp " + origini + " " + ini, shell=True)

	# decoder command
	decodercommand = "echo \"" + inputSent + "\" | " + cfgvar[MOSES_BIN_DIR] + "/moses_chart -f " + ini
	if args.kbest:
		decodercommand += (" -n-best-list " + dirname + "kbest " + str(args.kbest))
	if args.distinct:
		decodercommand += (" distinct")
	if args.decodersettings:
		decodercommand += " " + args.decodersettings
	if args.trace:
		decodercommand += " -T " + dirname + "trace"
	decodercommand += " > " + dirname + "trans 2>" + dirname + "decode.STDERR"
	sys.stderr.write("executing: " + decodercommand)
	call(decodercommand, shell=True)

	# bleu command
	# if kbest, evaluate the bleu score of the kbest list
	if args.bleu:
		if args.kbest:
			trans = dirname + "ktrans"
			transFile = open(trans, 'w')
			kbestFile = open(dirname + "kbest", 'r')
			for line in kbestFile:
				cells = line.split("|||")
				transFile.write(cells[1].strip() + "\n")
			transFile.close()
			kbestFile.close()
		else:
			trans = dirname + "trans"
		bleucommand = "cat " + trans + " | " + cfgvar[MOSES_BIN_DIR] + "/sentence-bleu " + " ".join(refs) + " > " + dirname + "bleu 2>" + dirname + "bleu.STDERR"
		sys.stderr.write("executing: " + bleucommand)
		call(bleucommand, shell=True)

	# TODO: generate report
	if args.outputFile:
		reportFile = open(args.outputFile, 'w')
	else:
		reportFile = open(dirname + "report.md", 'w')
	reportFile.write(\
			"+ Datetime: " + now.strftime("%m/%d/%Y %H:%M:%S") + "\n" +\
			"+ Working Directory: " + cfgvar[MOSES_WORKING_DIR] + "\n" +\
			"+ Run Number: " + cfgvar[RUN_NUMBER] + "\n" +\
			"+ Input File: " + inputFile + "\n" +\
			"+ Refernece File: " + ": ".join(origrefs) + "\n" +\
			"+ Sentence ID: " + args.sentenceid + "\n" +\
			"+ Decoder Command: " + decodercommand + "\n\n---\n\nOutput:\n\n")
	if args.kbest and args.bleu:
		# get the first line and parse it
		kbestFile = open(dirname + "kbest", 'r')
		bleuFile = open(dirname + "bleu", 'r')

		kbestline = kbestFile.readline()
		bleu = bleuFile.readline()
		items = kbestline.split("|||")
		outputSent = items[1].strip()
		rawBreakupScore = items[2].strip()
		overallScore = items[3].strip()

		# build table head and first line
		vars = []
		vals = []
		numPattern = re.compile("-?[0-9]+\.?[0-9]+")
		breakupTokens = breakupScores.split(' ')
		for tok in breakupTokens:
			if not numPattern.match(tok):
				var = tok[:-1]
			else:
				vals.append(float(tok))
				vars.append(var)
		table = []
		# build table as list and then transform that into html

	elif args.kbest:

	else:
		# zhe shi'er buhaoban

