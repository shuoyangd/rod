#! /usr/bin/python
import argparse
import sys
import io
import datetime
import re
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

def table2html(table, width=1, head=True, nu=False):
	res = "<table border=\"1\" width=\"" + str(int(width * 100)) + "%\">\n"
	ishead = True
	linen = 0
	for row in table:
		res += "\t<tr>"
		if ishead and nu:
			res += ("<td>#</td>")
		elif nu:
			res += ("<td>" + str(linen) + "</td>")
		for cell in row:
			res += ("<td>" + cell + "</td>")
		res += "</tr>\n"
		ishead = False
		linen += 1
	res += "</table>\n"
	return res

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
		inputDir = inputFile
		inputFile = open(inputFile, 'r')
	else:
		inputDir = cfgvar[MOSES_WORKING_DIR] + "/evaluation/" + cfgvar[CORPORA_NAME] + ".input.tc." + cfgvar[RUN_NUMBER]
		inputFile = open(inputDir, 'r')
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
	feats = []
	if args.force:
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
	kbest = dirname + "kbest"
	trans = dirname + "trans"
	trace = dirname + "trace"
	err = dirname + "decode.STDERR"
	decodercommand = "echo \"" + inputSent + "\" | " + cfgvar[MOSES_BIN_DIR] + "/moses_chart -f " + ini
	if args.kbest:
		decodercommand += (" -n-best-list " + kbest + " " + str(args.kbest))
	if args.distinct:
		decodercommand += (" distinct")
	if args.decodersettings:
		decodercommand += " " + args.decodersettings
	if args.trace:
		decodercommand += " -T " + trace
	decodercommand += " > " + trans + " 2>" + err
	sys.stderr.write("executing: " + decodercommand + "\n")
	call(decodercommand, shell=True)

	# bleu command
	# if kbest, evaluate the bleu score of the kbest list
	if args.bleu:
		if args.kbest:
			trans = dirname + "ktrans"
			transFile = open(trans, 'w')
			kbestFile = open(kbest, 'r')
			for line in kbestFile:
				cells = line.split("|||")
				transFile.write(cells[1].strip() + "\n")
			transFile.close()
			kbestFile.close()
		bleucommand = "cat " + trans + " | " + cfgvar[MOSES_BIN_DIR] + "/sentence-bleu " + " ".join(refs) + " > " + dirname + "bleu 2>" + dirname + "bleu.STDERR"
		sys.stderr.write("executing: " + bleucommand + "\n")
		call(bleucommand, shell=True)

	# generate report
	if args.outputFile:
		reportFile = open(args.outputFile, 'w')
	else:
		reportFile = open(dirname + "report.html", 'w')
	reportFile.write(\
			"<!DOCTYPE html>\n<html>\n<meta http-equiv=\"Content-Type\" content=\"text/html; charset=utf-8\" />\n<body>\n<ul>" +\
			"<li> Datetime: " + now.strftime("%m/%d/%Y %H:%M:%S") + "</li>\n" +\
			"<li> Working Directory: " + cfgvar[MOSES_WORKING_DIR] + "</li>\n" +\
			"<li> Run Number: " + cfgvar[RUN_NUMBER] + "</li>\n" +\
			"<li> Input File: " + inputDir + "</li>\n" +\
			"<li> Refernece File: " + ": ".join(origrefs) + "</li>\n" +\
			"<li> Sentence ID: " + str(args.sentenceid) + "</li>\n" +\
			"<li> Decoder Command: " + decodercommand + "</li></ul>\n\n<hr>\n\n<h2>Output:</h2>\n\n")
	# has option -k: extract from k-best list
	if args.kbest:
		# get the first line and parse it
		kbestFile = open(kbest, 'r')
		if args.bleu:
			bleuFile = open(dirname + "bleu", 'r')

		kbestline = kbestFile.readline()
		if args.bleu:
			bleu = bleuFile.readline().strip()
		items = kbestline.split("|||")
		outputSent = items[1].strip()
		rawBreakupScore = items[2]
		overallScore = items[3].strip()

		# build table head and first line
		vars = ["output sentence"]
		vals = [outputSent]
		numPattern = re.compile(r"[-+]?\d*\.\d+|\d+")
		breakupTokens = rawBreakupScore.split(' ')
		for tok in breakupTokens:
			tok = tok.strip()
			if not numPattern.match(tok):
				var = tok[:-1]
			else:
				vals.append(tok)
				vars.append(var)
		vals.append(overallScore)
		vars.append("overall score")
		if args.bleu:
			vals.append(bleu)
			vars.append("bleu")
		table = []
		table.append(vars)
		table.append(vals)
		# build table as list
		if args.bleu:
			for (kbestline, bleu) in zip(kbestFile, bleuFile):
				bleu = bleu.strip()
				items = kbestline.split("|||")
				outputSent = items[1].strip()
				rawBreakupScore = items[2]
				overallScore = items[3].strip()
				# output sentence as the first col
				vals = [outputSent]
				breakupTokens = rawBreakupScore.split(' ')
				for tok in breakupTokens:
					tok = tok.strip()
					if numPattern.match(tok):
						vals.append(tok)
				# bleu score as the last col
				vals.append(overallScore)
				vals.append(bleu)
				table.append(vals)
		else:
			for kbestline in kbestFile:
				items = kbestline.split("|||")
				outputSent = items[1].strip()
				rawBreakupScore = items[2]
				overallScore = items[3].strip()
				# output sentence as the first col
				vals = [outputSent]
				breakupTokens = rawBreakupScore.split(' ')
				for tok in breakupTokens:
					tok = tok.strip()
					if numPattern.match(tok):
						vals.append(tok)
				vals.append(overallScore)
				table.append(vals)
		# transform that into html
		tabhtml = table2html(table, 1.5, nu=True)
		reportFile.write(tabhtml)
	# no option -k: extract from decode stderr output and .ini file
	else:
		# collect feature names
		ini = dirname + "moses.ini"
		iniFile = open(ini, 'r')
		feats = ["output sentence"]
		isFeature = False
		for line in iniFile:
			if isFeature and line.strip() == "":
				isFeature = False
			elif isFeature:
				featToks = line.split(' ')
				if len(featToks) == 1:
					feats.append(line.strip())
				else:
					featname = None
					featnum = 1
					for featTok in featToks:
						if featTok.startswith("name"):
							featname = featTok[featTok.find('=') + 1:].strip()
						if featTok.startswith("num-features"):
							featnum = featTok[featTok.find('=') + 1:].strip()
					if featname:
						for i in range(0, int(featnum)):
							feats.append(featname)
			if line.strip() == "[feature]":
				isFeature = True
		iniFile.close()

		# collect scores
		overallScore = None
		breakupScore = None
		errFile = open(err, 'r')
		numPattern = re.compile(r"[-+]?\d*\.\d+|\d+")
		for line in errFile:
			if line.startswith("BEST TRANSLATION"):
				toks = line.split(' ')
				overallScore = numPattern.search(toks[-3]).group(0)
				breakupScore = numPattern.findall(toks[-2])
		errFile.close()

		# collect output sentence
		transFile = open(trans, 'r')
		outputSent = transFile.readline()

		# form feats and scores
		feats.append("overall score")
		score = [outputSent]
		if overallScore:
			score.append(overallScore)
		if breakupScore:
			score.extend(breakupScore)

		# collect bleu score, if there is one
		if args.bleu:
			bleuFile = open(dirname + "bleu", 'r')
			bleu = bleuFile.readline()
			feats.append("bleu")
			score.append(bleu)
		
		table = [feats, score]
		tabhtml = table2html(table, 1.5, nu=True)
		reportFile.write(tabhtml)
	reportFile.write("</body>\n</html>\n")
	reportFile.close()
