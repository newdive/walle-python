#coding=utf-8
#created by SamLee 2018/10/16
import json
import os
import tokenize
import io
import random
import string
import re

CONFIGKEY_DEFAULTEXTRA = 'defaultExtraInfo'
CONFIGKEY_CHANNELLIST = 'channelInfoList'

CONFIGKEY_CHANNEL_EXTRA = 'extraInfo'
CONFIGKEY_OUTPUT = 'output'

DEFAULT_OUTPUT_FOLDER = "channels"

'''
python doc string style is with tripple single quotes or tripple double quotes at start and end
'''
def isPyDocToken(tok):
    tokType, tokVal = tok[0], tok[1]
    return tokType==tokenize.STRING and \
            (tokVal[0:3]==tokVal[-3:]=='\'\'\'' or tokVal[0:3]==tokVal[-3:]=='\"\"\"')


def tryStripCommentTokens(tokens):
    def isCommentBlockStart(curTok,nextTok):
        return nextTok is not None and curTok[0]==nextTok[0]==tokenize.OP \
                and curTok[1]=='/' and (nextTok[1]=='*' or nextTok[1]=='**')
            
    def isCommentBlockEnd(curTok,nextTok):
        return nextTok is not None and curTok[0]==nextTok[0]==tokenize.OP \
                and (curTok[1]=='*' or curTok[1]=='**') and nextTok[1][0]=='/'
    
    lineCommentStartToken = '//'
    tokIdx, toksCount, nonCommentTokens = 0, len(tokens), []
    blockCommentStart, lineCommentStart = False, False
    
    while tokIdx<toksCount:
        curTok, nextTok = tokens[tokIdx],tokens[tokIdx+1] if tokIdx+1<toksCount else None
        #handle block-comment
        _blockStart = not blockCommentStart and isCommentBlockStart(curTok,nextTok)
        _blockEnd = blockCommentStart and isCommentBlockEnd(curTok,nextTok)
        if _blockStart or _blockEnd:
            blockCommentStart = True if _blockStart else False                   
            tokIdx += 2
            continue
               
        #handle line-comment 
        if not blockCommentStart:
            if lineCommentStart and (curTok[0]==tokenize.NL or curTok[0]==tokenize.NEWLINE):
                lineCommentStart = False
            if not lineCommentStart and curTok[0]==tokenize.OP and curTok[1]==lineCommentStartToken:
                lineCommentStart = True

        if not blockCommentStart and not lineCommentStart: 
            nonCommentTokens.append(curTok)
        tokIdx += 1

    return nonCommentTokens

'''
eliminate c-style or python-style comments from json file
including line and block comments/doc strings
note python tokenize recognize '//'  before '/'
'''
def stripComments(file):
    wholeStr = '\n'.join([line.strip() for line in file if len(line.strip())>0])
    # make all emptyComment block /**/ non empty, for better parsing
    replacers = []
    stringReplacements = [
        ("/**/", "/*{}*/", "\/\*[ ]+\*\/"),   #tokenizer treat ** as a operator prior to *
        ("*///", "*/{}//", "\*\/[ ]+\/\/")	  #tokenizer treat // as a operator prior to /
    ]
    for replacement in stringReplacements:
        replacee, replacer, replacePattern = replacement
        if not replacee in wholeStr:
            continue
        matches = re.findall(replacePattern, wholeStr)
        replId = max([len(re.findall('[ ]+',match)[0]) for match in matches])+1 if len(matches)>0 else 1
        replacer = replacer.format(' '*replId)
        wholeStr = wholeStr.replace(replacee,replacer)
        replacers.append((replacee,replacer))
    
    allToks = tokenize.generate_tokens(io.StringIO(wholeStr).readline)
    # exclude all possible comments and doc strings token
    nonCommentToks = [(tok[0],tok[1]) for tok in allToks if tok[0]!=tokenize.COMMENT and not isPyDocToken(tok)]
    nonCommentTokensFinal = tryStripCommentTokens(nonCommentToks)

    unCommenttedStr = tokenize.untokenize(nonCommentTokensFinal)
	#try fix possible previous misreplacements
    for replacer in replacers:
        unCommenttedStr = unCommenttedStr.replace(replacer[1],replacer[0])
    
    return unCommenttedStr


def loadConfig(configPath):
    global CONFIGKEY_CHANNELLIST, CONFIGKEY_DEFAULTEXTRA, CONFIGKEY_CHANNEL_EXTRA
    channelConfig = {CONFIGKEY_CHANNELLIST:[]}
    if configPath and os.path.exists(configPath):
        configStr = ''
        with open(configPath,'r',encoding='utf-8') as fh:
            configStr = stripComments(fh)

        channelConfig = json.loads(configStr)
        if not CONFIGKEY_CHANNELLIST in channelConfig:
            channelConfig[CONFIGKEY_CHANNELLIST] = []

        if CONFIGKEY_DEFAULTEXTRA in channelConfig and len(channelConfig[CONFIGKEY_DEFAULTEXTRA]):
            for cConfig in channelConfig[CONFIGKEY_CHANNELLIST]:
                configExtra = channelConfig[CONFIGKEY_DEFAULTEXTRA].copy()
                #override values
                if CONFIGKEY_CHANNEL_EXTRA in cConfig:
                    configExtra.update(cConfig[CONFIGKEY_CHANNEL_EXTRA])
                #channel is not overridable
                del configExtra[apk_util.CHANNEL_KEY]
                cConfig[CONFIGKEY_CHANNEL_EXTRA] = configExtra
  
    return channelConfig

