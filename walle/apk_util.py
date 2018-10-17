#coding=utf-8
#created by SamLee 2018/10/14
import sys
import os
import json
import traceback
import zipfile

'''
 APK Signing Block Magic Code: magic “APK Sig Block 42” (16 bytes)
 "APK Sig Block 42" : 41 50 4B 20 53 69 67 20 42 6C 6F 63 6B 20 34 32
'''
APK_SIG_BLOCK_MAGIC_HI = 0x3234206b636f6c42 #LITTLE_ENDIAN, High
APK_SIG_BLOCK_MAGIC_LO = 0x20676953204b5041 # LITTLE_ENDIAN, Low
APK_SIG_BLOCK_MIN_SIZE = 32

'''
The v2 signature of the APK is stored as an ID-value pair with ID 0x7109871a
(https://source.android.com/security/apksigning/v2.html#apk-signing-block)
'''
APK_SIGNATURE_SCHEME_V2_BLOCK_ID = 0x7109871a

#Walle Channel Block ID
APK_CHANNEL_BLOCK_ID = 0x71777777

DEFAULT_CHARSET = "UTF-8"
ENDIAN = 'little'

ZIP_EOCD_REC_MIN_SIZE = 22
ZIP_EOCD_REC_SIG = 0x06054b50
UINT16_MAX_VALUE = 0xffff
ZIP_EOCD_COMMENT_LENGTH_FIELD_OFFSET = 20

CHANNEL_KEY = "channel"



DEXHEAD_MAGICS = [bytes.fromhex('64 65 78 0A 30 33'),\
                    bytes.fromhex('64 65 79 0A 30 33')]

CHUNK_XML,CHUNK_STRING,CHUNK_TABLE,CHUNK_TABLEPACKAGE  = 0x0003,0x0001,0x0002,0x0200

def getFileSize(f):
    org_pos = f.tell()
    try:
        f.seek(0, os.SEEK_END)
        return f.tell()
    finally:
        f.seek(org_pos, os.SEEK_SET)

def getActualFileSize(f,bytesRead):
    if f.seekable():
        return getFileSize(f)
    #not seekable , has to advance to the end
    return bytesRead + len(f.read())

'''
verify arsc file header and file size information
'''
def isPossibleArsc(arscFile,arscInfo=None):
    global ENDIAN, CHUNK_TABLE,CHUNK_STRING, CHUNK_TABLEPACKAGE
    headInfo = arscFile.read(8)
    expectedChunkSize,actualChunkSize = int.from_bytes(headInfo[4:8],ENDIAN) , 0
    if len(headInfo)<8 or int.from_bytes(headInfo[0:2],ENDIAN) != CHUNK_TABLE:
        return False
    actualChunkSize += 8 + len( arscFile.read(int.from_bytes(headInfo[2:4],ENDIAN) - 8) )
    headInfo = arscFile.read(8)
    if len(headInfo)<8 or int.from_bytes(headInfo[0:2],ENDIAN) != CHUNK_STRING:
        return False
    actualChunkSize += 8 + len( arscFile.read(int.from_bytes(headInfo[4:8],ENDIAN) - 8) )
    headInfo = arscFile.read(8)
    if len(headInfo)<8 or int.from_bytes(headInfo[0:2],ENDIAN) != CHUNK_TABLEPACKAGE:
        return False
    actualChunkSize = arscInfo.file_size if arscInfo is not None else getActualFileSize(arscFile,actualChunkSize + 8) 
    return expectedChunkSize== actualChunkSize

'''
verify the binary xml file format
not including the tag format of application,activity,service,permission and the like 
'''
def isPossibleManifest(manifest,manifestInfo=None):
    global ENDIAN,CHUNK_XML,CHUNK_STRING
    manifestHeaders = manifest.read(16)
    if not manifestHeaders or len(manifestHeaders)<16:
        return False
    xmlHead = int.from_bytes(manifestHeaders[0:2],ENDIAN)
    xmlChunkSize = int.from_bytes(manifestHeaders[4:8],ENDIAN)
    strHead = int.from_bytes(manifestHeaders[8:10],ENDIAN)
    actualFileSize = manifestInfo.file_size if manifestInfo is not None else getActualFileSize(manifest, 16) 
    return xmlHead==CHUNK_XML and strHead==CHUNK_STRING and xmlChunkSize==actualFileSize

'''
verify the dex file header and dex file size information
'''
def isPossibleDexFile(dexFile,dexInfo=None):
    global DEXHEAD_MAGICS
    apkHead = dexFile.read(8)
    if len(apkHead)<8 or not (apkHead[0:6] in DEXHEAD_MAGICS and apkHead[-1]==0):
        return False
    #skip checksum and signature
    dexFile.read(24)
    dexFileSize = int.from_bytes(dexFile.read(4),ENDIAN)
    actualFileSize = dexInfo.file_size if dexInfo is not None else getActualFileSize(dexFile, 8 + 24 + 4)
    return dexFileSize==actualFileSize

'''
verify three types of file format in apk archive
AndroidManifest.xml, resources.arsc, *.dex
it is a possible apk if it passes all the above verifications
'''
def isPossibleApkFile(filePath):
    try:
        manifestVerify,dexVerify, arscVerify = [], [], []
        with zipfile.ZipFile(filePath,'r') as apkArc:
            for zipInfo in apkArc.infolist():
                if zipInfo.filename=='AndroidManifest.xml':
                    with apkArc.open(zipInfo.filename,'r') as manifest:
                        manifestVerify.append( isPossibleManifest(manifest,zipInfo) )
                elif zipInfo.filename=='resources.arsc':
                    with apkArc.open(zipInfo.filename,'r') as arsc:
                        arscVerify.append( isPossibleArsc(arsc,zipInfo) )
                elif zipInfo.filename.startswith('classes') and zipInfo.filename.endswith('.dex'):
                    with apkArc.open(zipInfo.filename,'r') as apkDex:
                        dexVerify.append( isPossibleDexFile(apkDex,zipInfo) )

            if len(manifestVerify)!=1: manifestVerify.append(False)
            if len(dexVerify)<1: dexVerify.append(False)
        #print(manifestVerify,dexVerify,arscVerify)
        return all(manifestVerify) and all(dexVerify) and all(arscVerify)
    except:
        #traceback.print_exc()
        return False

'''
End of central directory record (EOCD)
Offset    Bytes     Description[23]
0           4       End of central directory signature = 0x06054b50
4           2       Number of this disk
6           2       Disk where central directory starts
8           2       Number of central directory records on this disk
10          2       Total number of central directory records
12          4       Size of central directory (bytes)
16          4       Offset of start of central directory, relative to start of archive
20          2       Comment length (n)
22          n       Comment
For a zip with no archive comment, the
end-of-central-directory record will be 22 bytes long, so
we expect to find the EOCD marker 22 bytes from the end.

ZIP End of Central Directory (EOCD) record is located at the very end of the ZIP archive.
The record can be identified by its 4-byte signature/magic which is located at the very
beginning of the record. A complication is that the record is variable-length because of
the comment field.
The algorithm for locating the ZIP EOCD record is as follows. We search backwards from
end of the buffer for the EOCD record signature. Whenever we find a signature, we check
the candidate record's comment length is such that the remainder of the record takes up
exactly the remaining bytes in the buffer. The search is bounded because the maximum
size of the comment field is 65535 bytes because the field is an unsigned 16-bit number.
final long maxCommentLength = Math.min(archiveSize - ZIP_EOCD_REC_MIN_SIZE, UINT16_MAX_VALUE);

'''
def getCommentLength(apkFile):
    global ENDIAN,ZIP_EOCD_REC_MIN_SIZE, UINT16_MAX_VALUE, \
            ZIP_EOCD_REC_SIG, ZIP_EOCD_COMMENT_LENGTH_FIELD_OFFSET

    archiveSize = getFileSize(apkFile)
    if archiveSize < ZIP_EOCD_REC_MIN_SIZE:
        raise Exception("APK too small for ZIP End of Central Directory (EOCD) record");

    maxCommentLength = min(archiveSize - ZIP_EOCD_REC_MIN_SIZE, UINT16_MAX_VALUE);
    eocdWithEmptyCommentStartPosition = archiveSize - ZIP_EOCD_REC_MIN_SIZE
    for expectedCommentLength in range(0,maxCommentLength+1):
        eocdStartPos = eocdWithEmptyCommentStartPosition - expectedCommentLength
        apkFile.seek(eocdStartPos,os.SEEK_SET)
        readBuffer = apkFile.read(4)
        if int.from_bytes(readBuffer, ENDIAN) == ZIP_EOCD_REC_SIG:
            apkFile.seek(eocdStartPos + ZIP_EOCD_COMMENT_LENGTH_FIELD_OFFSET,os.SEEK_SET)
            readBuffer = apkFile.read(2)
            actualCommentLength = int.from_bytes(readBuffer, ENDIAN)
            if actualCommentLength == expectedCommentLength:
                return actualCommentLength

    raise Exception("ZIP End of Central Directory (EOCD) record not found");

'''
End of central directory record (EOCD)
Offset    Bytes     Description[23]
0           4       End of central directory signature = 0x06054b50
4           2       Number of this disk
6           2       Disk where central directory starts
8           2       Number of central directory records on this disk
10          2       Total number of central directory records
12          4       Size of central directory (bytes)
16          4       Offset of start of central directory, relative to start of archive
20          2       Comment length (n)
22          n       Comment
For a zip with no archive comment, the
end-of-central-directory record will be 22 bytes long, so
we expect to find the EOCD marker 22 bytes from the end.
'''
def findCentralDirStartOffset(apkFile):
    global ENDIAN
    archiveSize = getFileSize(apkFile)
    commentLength = getCommentLength(apkFile)
    #6 = 2 (Comment length) + 4 (Offset of start of central directory, relative to start of archive)
    apkFile.seek(archiveSize-commentLength-6, os.SEEK_SET)
    return int.from_bytes(apkFile.read(4), ENDIAN)

'''
Find the APK Signing Block. The block immediately precedes the Central Directory.

FORMAT:
OFFSET       DATA TYPE  DESCRIPTION
* @+0  bytes uint64:    size in bytes (excluding this field)
* @+8  bytes payload
* @-24 bytes uint64:    size in bytes (same as the one above)
* @-16 bytes uint128:   magic
'''
def findApkSigningBlock(apkFile,centralDirOffset):
    global ENDIAN, APK_SIG_BLOCK_MIN_SIZE, APK_SIG_BLOCK_MAGIC_LO, APK_SIG_BLOCK_MAGIC_HI

    if centralDirOffset < APK_SIG_BLOCK_MIN_SIZE:
        raise Exception("APK too small for APK Signing Block. ZIP Central Directory offset: {}".format(centralDirOffset))
    '''
     Read the magic and offset in file from the footer section of the block:
     * uint64:   size of block
     * 16 bytes: magic
    '''
    apkFile.seek(centralDirOffset - 24, os.SEEK_SET)
    readBuffer = apkFile.read(24)
    if int.from_bytes(readBuffer[8:8+8],ENDIAN)!=APK_SIG_BLOCK_MAGIC_LO \
        or int.from_bytes(readBuffer[16:16+8],ENDIAN)!=APK_SIG_BLOCK_MAGIC_HI:
        raise Exception("No APK Signing Block before ZIP Central Directory")
    # Read and compare size fields
    apkSigBlockSizeInFooter = int.from_bytes(readBuffer[0:8],ENDIAN)
    if apkSigBlockSizeInFooter<24 or apkSigBlockSizeInFooter>0x7fffffff -8:
        raise Exception("APK Signing Block size out of range: {}".format(apkSigBlockSizeInFooter))
    
    totalSize = apkSigBlockSizeInFooter + 8
    apkSigBlockOffset = centralDirOffset - totalSize
    if apkSigBlockOffset < 0 :
        raise Exception( "APK Signing Block offset out of range: {}".format(apkSigBlockOffset))
    
    apkFile.seek(apkSigBlockOffset,os.SEEK_SET)
    apkSigBlock = apkFile.read(totalSize)
    apkSigBlockSizeInHeader = int.from_bytes(apkSigBlock[0:8],ENDIAN)
    if apkSigBlockSizeInHeader != apkSigBlockSizeInFooter:
        raise Exception("APK Signing Block sizes in header and footer do not match: {} vs {}".format(apkSigBlockSizeInHeader,apkSigBlockSizeInFooter))
    
    return apkSigBlock,apkSigBlockOffset

'''
FORMAT:
OFFSET       DATA TYPE  DESCRIPTION
* @+0  bytes uint64:    size in bytes (excluding this field)
* @+8  bytes pairs
* @-24 bytes uint64:    size in bytes (same as the one above)
* @-16 bytes uint128:   magic
'''
def findSigningBlockValues(apkSigningBlock):
    global ENDIAN
    idValues = {}
    pairStart, pairEnd  = 8, len(apkSigningBlock) - 24
    if pairEnd < pairStart:
        raise Exception("end < start: {} < {}".format(pairEnd,pairStart))
    pairs = apkSigningBlock[pairStart:pairEnd]
    #print('apkSigningBlock:',len(pairs),'content:',pairs)
    entryCount = 0
    pairsPos,pairsLen = 0, len(pairs)

    while pairsLen>pairsPos:
        entryCount += 1
        if pairsLen-pairsPos < 8:
            raise Exception("Insufficient data to read size of APK Signing Block entry #}{".format(entryCount))
        lenLong = int.from_bytes(pairs[pairsPos:pairsPos+8],ENDIAN)
        pairsPos += 8
        
        if lenLong<4 or lenLong>0x7fffffff:
            raise Exception("APK Signing Block entry #{} size out of range: {}".format(entryCount,lenLong))

        nextEntryPos = pairsPos + lenLong;
        if lenLong > pairsLen-pairsPos:
            raise Exception("APK Signing Block entry #{} size out of range: {}, available: ".format(entryCount,lenLong,pairsLen-pairsPos))
        
        entryId = int.from_bytes(pairs[pairsPos:pairsPos+4],ENDIAN)
        pairsPos += 4
        idValues[entryId] = pairs[pairsPos : pairsPos + lenLong - 4]
        
        pairsPos = nextEntryPos

    return idValues


'''
get all custom (id, bytes) <br/>

param apkFile apk file
return all custom (id, bytes)
'''
def getAllSignInfo(apkFilePath):
    signIdValues,apkSignErr = None,None
    with open(apkFilePath,'rb') as apkFile:
        try:
            centralDirOffset = findCentralDirStartOffset(apkFile);
            apkSigningBlock2,apkSigningBlock2Offset = findApkSigningBlock(apkFile,centralDirOffset)
            signIdValues = findSigningBlockValues(apkSigningBlock2)
        except Exception as err:
            apkSignErr = err
            #traceback.print_exc()
            pass
    return signIdValues,apkSignErr


