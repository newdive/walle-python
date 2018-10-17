#coding=utf-8
#created by SamLee 2018/10/17
import sys
import os
import traceback

import time
import optparse
import json
import shlex
import shutil
import multiprocessing
import threading
import pathlib

from walle import apk_util, walle_writer, walle_reader, channel_config


def displayApkSignInfo(apkFiles,options):
    if len(apkFiles)<1:
        print('没有需要显示的apk文件')
        return
    if not options.viewChannel and not options.viewRaw:
        # do nothing
        return 
    
    channelSignedApks = 0
    for apkFile in apkFiles:
        info = None
        if options.viewRaw:
            info,_ = apk_util.getAllSignInfo(apkFile)
        elif options.viewChannel:
            info = walle_reader.getChannelInfo(apkFile)
        if not info:
            continue
        
        channelSignedApks += 1
        print('>'*8)
        print('{} <{}>'.format(os.path.basename(apkFile), os.path.dirname(apkFile)))
        
        if options.viewChannel:
            print('\tchannel:{}'.format(info[apk_util.CHANNEL_KEY] if apk_util.CHANNEL_KEY in info else ''))
            if len(info)>1:
                print('\textra:')
            for key,value in info.items():
                if key!=apk_util.CHANNEL_KEY: 
                    print('\t\t{} : {}'.format(key,value))
        else:
            for id,value in info.items():
                print('\t{} : {}'.format(id,value))
        print('<'*8)
    
    print('\n共检测到 {} 个apk含有渠道信息。'.format(channelSignedApks))

def genApk(targetApk,channelConfig, msgQueue=None):
    outputPath = channelConfig[channel_config.CONFIGKEY_OUTPUT]
    del channelConfig[channel_config.CONFIGKEY_OUTPUT]
    #generate new file
    signInfo,genException = apk_util.getAllSignInfo(targetApk)
    genApkPath, acceptedChannelConfig = None, channelConfig
    if signInfo is not None :
        genApkPath, hasCreateCopy = None, True
        if outputPath!=targetApk:
            channelName = channelConfig[apk_util.CHANNEL_KEY]
            apkName = os.path.basename(targetApk)
            extIdx = apkName.rfind('.')
            apkNameWithChannel = apkName[0:extIdx] + '_' + channelName + apkName[extIdx:] if extIdx>-1 else apkName+'_'+channelName
            genApkPath = os.path.join(outputPath,apkNameWithChannel)
            
            apkOutputFolder = os.path.dirname(genApkPath)
            if not os.path.exists(apkOutputFolder):
                print(apkOutputFolder,'not exists')
                os.makedirs(apkOutputFolder)

            shutil.copyfile(targetApk,genApkPath)
            hasCreateCopy = True
        else:
            genApkPath = targetApk
        print(targetApk,'=>',genApkPath)
        acceptedChannelConfig = {}
        if channel_config.CONFIGKEY_CHANNEL_EXTRA in channelConfig:
            acceptedChannelConfig.update(channelConfig[channel_config.CONFIGKEY_CHANNEL_EXTRA])
        acceptedChannelConfig[apk_util.CHANNEL_KEY] = channelConfig[apk_util.CHANNEL_KEY]
        
        genException = None
        try:
            walle_writer.putChannelInfo(genApkPath,acceptedChannelConfig)
        except Exception as err:
            if hasCreateCopy: os.remove(genApkPath)
            x = err

    if msgQueue is not None:
        msgQueue.put((targetApk,genException if genException is not None else genApkPath,acceptedChannelConfig))

def acquireChannelConfigFromInput(options):
    channel,extraInfo = '', None
    while len(channel)<1:
        channel = input('请输入渠道名称:').strip()
    extraStr = input('请输入额外信息(key=value...):').strip()
    if len(extraStr):
        try:
            extraInfo = {kvPair.split('=')[0].strip():kvPair.split('=')[1].strip() for kvPair in shlex.split(extraStr)}
        except:
            print('忽略额外信息...')
    return {apk_util.CHANNEL_KEY:channel, channel_config.CONFIGKEY_CHANNEL_EXTRA:extraInfo}

def generateApkWithChannel(targetApks,channelConfigs,options):
    if len(targetApks)<1:
        print('没有需要处理的apk文件')
        return
    
    outputPath = options.output
    if outputPath and not os.path.exists(outputPath):
        os.makedirs(outputPath)
        
    if len(channelConfigs)<1 or len(channelConfigs[channel_config.CONFIGKEY_CHANNELLIST])<1:
        channelConfigs[channel_config.CONFIGKEY_CHANNELLIST].append(acquireChannelConfigFromInput(options))
    
    procPool, msgQueue = options.__procPool, options.__msgQueue
    
    def genAllApks(procPool,msgQueue,targetApks,channelConfigs):
        for targetApk in targetApks:
            for cConfig in channelConfigs:
                cConfig = cConfig.copy()
                defaultFolder = channel_config.DEFAULT_OUTPUT_FOLDER
                defaultOutputPath = os.path.join(os.path.dirname(targetApk),defaultFolder) if not outputPath else outputPath
                outputKey = channel_config.CONFIGKEY_OUTPUT
                cConfig[outputKey] = defaultOutputPath if not outputKey in cConfig else cConfig[outputKey] 
                if procPool is not None:
                    procPool.apply_async(genApk, args=(targetApk,cConfig,msgQueue))
                else:
                    genApk(targetApk,cConfig,msgQueue)

    genTh = threading.Thread(target=genAllApks,args=(procPool,msgQueue,targetApks,channelConfigs[channel_config.CONFIGKEY_CHANNELLIST]))
    genTh.start()
    
    print('\n准备生成渠道信息...')
    genInfoMap = {}
    genCount,expectedCount = 0, len(targetApks)*len(channelConfigs[channel_config.CONFIGKEY_CHANNELLIST])
    continuousWait = 0
    while genCount<expectedCount:
        if msgQueue.empty():
            time.sleep(1)
            continuousWait += 1
            if continuousWait>60:
                print("wait too long queue is empty=>",genCount,",",expectedCount)
            continue
        continuousWait = 0
        targetApk, outputApk, writeConfig = msgQueue.get_nowait()
        genCount += 1
        genInfoMap[targetApk] = {'output':outputApk,'channelConfig':writeConfig}
        msgQueue.task_done()
        if isinstance(outputApk,Exception) or not os.path.exists(outputApk):
            print("{} 生成渠道信息失败:".format(os.path.basename(targetApk)))
            print("\t{}".format(outputApk))
        else:
            print('{} => {}'.format(os.path.basename(targetApk), outputApk))
            print('{} => {}'.format(' '*len(os.path.basename(targetApk)), writeConfig))

    return genInfoMap

def eraseApkChannelInfo(targetApk,msgQueue=None):
    channelInfo = walle_reader.getChannelInfo(targetApk)
    if channelInfo is not None:
        walle_writer.removeChannelInfo(targetApk)
    if msgQueue is not None:
        msgQueue.put((targetApk,channelInfo))

def eraseAllApkChannelInfo(targetApks,options):
    if len(targetApks)<1:
        print('没有需要清除渠道信息的apk文件')
        return

    procPool, msgQueue = options.__procPool, options.__msgQueue
    
    def eraseChannelInfos(procPool,msgQueue,targetApks):
        for targetApk in targetApks:
            if procPool is not None:
                procPool.apply_async(eraseApkChannelInfo,args=(targetApk,msgQueue))
            else:
                eraseApkChannelInfo(targetApk,msgQueue)
    
    eraseTh = threading.Thread(target=eraseChannelInfos, args = (procPool,msgQueue,targetApks))
    eraseTh.start()
    print('\n准备清除渠道信息...')
    apkWithChannelCount, clearApkNum , totalApks = 0, 0, len(targetApks)
    while clearApkNum<totalApks:
        if not msgQueue.empty():
            targetApk, channelInfo = msgQueue.get_nowait()
            clearApkNum += 1
            if channelInfo is not None:
                apkWithChannelCount += 1
            msgQueue.task_done()
            if channelInfo is not None:
                print('渠道信息清除成功 => {}'.format(targetApk))

    print('\n清除渠道信息工作完成, 共清除了{}个apk的渠道信息'.format(apkWithChannelCount))


def verifyApk(msgQueue,apkFile):
    #print('startVerifying apk:',apkFile)
    isApk = apk_util.isPossibleApkFile(apkFile)
    msgQueue.put((apkFile,isApk))

def scanApkFiles(apkFiles,options):
    procResults = []
    
    def verifyAllFiles(procPool,msgQueue,apkFiles):
        if procPool is not None:
            [procPool.apply_async(verifyApk,args=(msgQueue,file)) for file in apkFiles]
        else:
            for file in apkFiles:
                isApk = apk_util.isPossibleApkFile(file)
                msgQueue.put((file,isApk))
    
    procPool, msgQueue = options.__procPool, options.__msgQueue
    checkTh = threading.Thread(target=verifyAllFiles,args=(procPool,msgQueue,apkFiles))
    checkTh.start()
    
    targetApks = []
    checkCount, totalFiles = 0, len(apkFiles)
    while checkCount<totalFiles:
        if not msgQueue.empty():
            checkCount += 1
            file,isApk = msgQueue.get_nowait()
            if isApk:
                targetApks.append(file)
            msgQueue.task_done()
            sys.stdout.write('\r检测 apk ({}/{})...'.format(checkCount,totalFiles))
            sys.stdout.flush()

    return targetApks



def main(options,args):
    
    channelConfigs, targetApks = {}, []
    try:
        channelConfigs = channel_config.loadConfig(options.config)
    except:
        print('{} 文件解析失败，请检查格式/编码是否有误。'.format(option.config))
    
    msgQueue = multiprocessing.Manager().Queue(0)
    procPool = None
    if options.parallel:
        procPool = multiprocessing.Pool(processes=max(2, multiprocessing.cpu_count() ) ) #multiprocessing.cpu_count()
    
    #print('using multiprocessing' if procPool is not None else 'using single process')
    
    options.ensure_value('__procPool',procPool)
    options.ensure_value('__msgQueue',msgQueue)

    if options.input and os.path.exists(options.input):
        startTime = time.time()
        scannedFiles = [file.as_posix() for file in pathlib.Path(options.input).glob('**/*.apk')] if os.path.isdir(options.input) else [options.input] 
        print('\n扫描 {} 个文件, 耗费 {} 秒'.format(len(scannedFiles),round(time.time()-startTime,3) ))
        if options.detect:
            startTime = time.time()
            targetApks = scanApkFiles(scannedFiles,options)
            print('\n共检测到 {} 个 apk, 耗时 {} 秒'.format(len(targetApks), round(time.time()-startTime,3) ))
            illegalApks = [file for file in scannedFiles if file not in targetApks]
            if len(illegalApks):
                print('{}\r\n...等 {} 个文件不是合法 apk'.format('\r\n'.join(illegalApks[0:5]),len(illegalApks)))
        else:
            targetApks = scannedFiles
    
    if options.viewRaw or options.viewChannel:
        displayApkSignInfo(targetApks,options)
    else:
        if not options.erase:
            generateApkWithChannel(targetApks,channelConfigs,options)
        else:
            eraseAllApkChannelInfo(targetApks,options)
    
    if procPool is not None:
        procPool.close()
        procPool.join()

def parseOptions():
    parser = optparse.OptionParser()
	
    parser.add_option('-p','--parallel',
        action='store_true',dest='parallel', 
        help='使用并行模式',default=False)
    
    parser.add_option('-d','--detect',
        action='store_true',dest='detect', 
        help='检测apk的合法性',default=False)

    parser.add_option('-v','--viewChannel',
        action='store_true',dest='viewChannel',
        help='查看渠道信息',default=False)

    parser.add_option('-r','--viewRaw',
        action='store_true',dest='viewRaw',
        help='查看所有的签名信息',default=False)
    
    parser.add_option('-e','--erase',
        action='store_true',dest='erase',
        help='清除渠道信息(会修改源apk!)',default=False)

    parser.add_option('-c','--config',
        action='store',dest='config',
        help='channel.json 文件路径',default=None)
    
    parser.add_option('-o','--output',
        action='store',dest='output',
        help='打包后输出的目录(默认为apk所在目录的 {} 文件夹下)'.format(channel_config.DEFAULT_OUTPUT_FOLDER),default=None)
       
    parser.add_option('-i','--input',
        action='store',dest='input',
        help='需要打包的apk文件/文件夹路径',default=None)
    
    return parser.parse_args()
	

if __name__ == '__main__':
    main(*parseOptions())
    