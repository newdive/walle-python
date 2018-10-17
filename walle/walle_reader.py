#coding=utf-8
#created by SamLee 2018/10/14
import os
import sys
import json
import traceback
import apk_util
import time

def getRawChannelStr(apkFilePath):
    signIdValues,signErr = apk_util.getAllSignInfo(apkFilePath)
    if signIdValues is None:
        return None
    valueBytes = signIdValues[apk_util.APK_CHANNEL_BLOCK_ID] if apk_util.APK_CHANNEL_BLOCK_ID in signIdValues else None
    if valueBytes is None:
        return None
    return valueBytes.decode(apk_util.DEFAULT_CHARSET)

def getChannelInfo(apkFilePath):
    channelRawStr = getRawChannelStr(apkFilePath)
    if channelRawStr is None:
        return None
    return json.loads(channelRawStr)

if __name__ == '__main__':
    args = sys.argv[1:]
    if len(args)<1:
        print('No apk file specified')
        sys.exit(0)
    apkFilePath = args[0]
    if not os.path.exists(apkFilePath):
        print('apk file[{}] not exist!'.format(apkFilePath))
        sys.exit(0)
    
    if not apk_util.isPossibleApkFile(apkFilePath):
        print('Not a legal apk!')
        sys.exit(0)

    channelInfo = getChannelInfo(apkFilePath)
    if channelInfo is None:
        print('No ChannelInfo detected!')
    else:
        print('ChannelInfo:')
        print('\tchannel:{}'.format(channelInfo[apk_util.CHANNEL_KEY]))
        print('\textraInfo:{}'.format({k:v for k,v in channelInfo.items() if k!=apk_util.CHANNEL_KEY},))
    