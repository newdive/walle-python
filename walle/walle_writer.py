#coding=utf-8
#created by SamLee 2018/10/14
import os
import sys
import json
import shlex
import apk_util
import walle_reader as reader

def writeSignIdValues(apkFile,idValues):
    if idValues is None:
        return
    #24 = 8(size of block in bytes—same as the very first field (uint64)) + 16 (magic “APK Sig Block 42” (16 bytes))
    length = 24
    for id,valueBytes in idValues.items():
        #12 = 8(uint64-length-prefixed) + 4 (ID (uint32))
        length += 12 + len(valueBytes)

    apkFile.write(length.to_bytes(8, apk_util.ENDIAN))

    for id,valueBytes in idValues.items():
        # Long.BYTES - Integer.BYTES
        valueBytesLen = len(valueBytes) + (8 - 4)
        apkFile.write(valueBytesLen.to_bytes(8, apk_util.ENDIAN))
        apkFile.write(id.to_bytes(4, apk_util.ENDIAN))
        apkFile.write(valueBytes)
    
    apkFile.write(length.to_bytes(8, apk_util.ENDIAN))
    apkFile.write(apk_util.APK_SIG_BLOCK_MAGIC_LO.to_bytes(8, apk_util.ENDIAN))
    apkFile.write(apk_util.APK_SIG_BLOCK_MAGIC_HI.to_bytes(8, apk_util.ENDIAN))
    
    return length

'''
add or remove info by id
if dataIdValues[id] is None ,it means to remove the specified id data from sign info
otherwise it means to add or update
'''
def modifySignInfo(apkFilePath,dataIdValues):
    if dataIdValues is None or len(dataIdValues)<1:
        return

    with open(apkFilePath,'r+b') as apkFile:
        fileSize = apk_util.getFileSize(apkFile)

        commentLength = apk_util.getCommentLength(apkFile)
        centralDirOffset = apk_util.findCentralDirStartOffset(apkFile);
        apkSigningBlock2,apkSigningBlock2Offset = apk_util.findApkSigningBlock(apkFile,centralDirOffset)
        signInfoIdValues = apk_util.findSigningBlockValues(apkSigningBlock2)

        if signInfoIdValues is None or not apk_util.APK_SIGNATURE_SCHEME_V2_BLOCK_ID in signInfoIdValues:
            raise Exception("No APK Signature Scheme v2 block in APK Signing Block")
        
        signInfoIdValues.update(dataIdValues)
        signInfoIdValues = {id:valueBytes for id,valueBytes in signInfoIdValues.items() if valueBytes is not None}

        apkFile.seek(centralDirOffset, os.SEEK_SET)
        centralDirBytes = apkFile.read(fileSize-centralDirOffset)
        
        apkFile.seek(apkSigningBlock2Offset, os.SEEK_SET)
        length = writeSignIdValues(apkFile,signInfoIdValues)

        apkFile.write(centralDirBytes);
        currentFileSize = apkFile.tell()

        apkFile.truncate()
        '''
        update CentralDir Offset
        End of central directory record (EOCD)
        Offset     Bytes     Description[23]
        0            4       End of central directory signature = 0x06054b50
        4            2       Number of this disk
        6            2       Disk where central directory starts
        8            2       Number of central directory records on this disk
        10           2       Total number of central directory records
        12           4       Size of central directory (bytes)
        16           4       Offset of start of central directory, relative to start of archive
        20           2       Comment length (n)
        22           n       Comment
        '''
        apkFile.seek(currentFileSize-commentLength - 6, os.SEEK_SET)
        # 6 = 2(Comment length) + 4 (Offset of start of central directory, relative to start of archive)
        # 8 = size of block in bytes (excluding this field) (uint64)
        eocdMrk = (centralDirOffset + length + 8 - (centralDirOffset - apkSigningBlock2Offset))
        apkFile.write(eocdMrk.to_bytes(4, apk_util.ENDIAN))

def removeChannelInfo(apkFilePath):
    modifySignInfo(apkFilePath,{apk_util.APK_CHANNEL_BLOCK_ID:None})

def putChannelInfo(apkFilePath,infoDict):
    if infoDict is None or len(infoDict)<1:
        return
    infoStr = json.dumps(infoDict,default=str)
    modifySignInfo(apkFilePath,{apk_util.APK_CHANNEL_BLOCK_ID : infoStr.encode(apk_util.DEFAULT_CHARSET)})
    

def printApkChannelInfo(apkFilePath):
    channelInfo = reader.getChannelInfo(apkFilePath)
    if channelInfo is None:
        print('\t{}')
    else:
        print('\tchannel:{}'.format(channelInfo[apk_util.CHANNEL_KEY]))
        print('\textraInfo:{}'.format({k:v for k,v in channelInfo.items() if k!=apk_util.CHANNEL_KEY},))

if __name__ == '__main__':
    args = sys.argv[1:]
    if len(args)<1:
        print('No apk file specified!')
        sys.exit(0)
    apkFilePath = args[0]
    if not os.path.exists(apkFilePath):
        print('Apk file[{}] does not exist!'.format(apkFilePath))
        sys.exit(0)

    if not apk_util.isPossibleApkFile(apkFilePath):
        print('Not a legal apk!')
        sys.exit(0)

    print('Current ChannelInfo:')
    printApkChannelInfo(apkFilePath)
    print('================================================')

    channel = input('Input channel : ').strip()
    extraStr = input('Input extraInfo[ key=value( key=value)* ] : ').strip()

    isRemove = False
    if len(channel)<1 and len(extraStr)<1:
        isRemove = input('You might want to clear channelInfo?(y/n) : ').strip().lower()=='y'
    
    if isRemove:
        removeChannelInfo(apkFilePath)
    else:
        channelInfo = {}
        if len(extraStr)>0:
            channelInfo.update({kvPair.split('=')[0].strip():kvPair.split('=')[1].strip() for kvPair in shlex.split(extraStr)})
        channelInfo[apk_util.CHANNEL_KEY] = channel
        putChannelInfo(apkFilePath,channelInfo)
    
    