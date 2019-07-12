# -*- coding: utf-8 -*-
# @Time    : 2019/7/11 10:32
# @Author  : hoo
# @Site    : 
# @File    : korok.py
# @Software: PyCharm Community Edition

'''
2019/7/9 : 日志清理脚本
'''

import codecs
import glob
import traceback
import tarfile
import subprocess
import sys
import datetime
import time
import shutil
import os
import logging
import optparse
import shlex
import socket
import fnmatch
import re
import platform
# python2 python3 import diff
from sys import version_info
if version_info.major == 2:
    import ConfigParser
else:
    import configparser as ConfigParser


'''
# 数据备份
[archive-eg]
action=archive
# 备份原路径
src=/home/ap/dev/app/logs
dst=/home/ap/dev/backup
pattern=/home/ap/dev/app/logs/2018*.log
# 备份文件是否带时间戳
timestamp=y
# 是否保存原文件
reserve=y
# day-hour-minute-second
mtime=0-0-0-01
'''


class Coper:

    def __init__(self, options, args):
        self.ConfigFile = options.filename
        self.NowTime = time.time()
        self.ExecTime = self.nowtime()
        self.Options = options
        self.Args = args
        self.HostNm = socket.gethostname()

        # log setting
        try:
            # debug level
            if options.debug == 'True':
                loglevel = logging.DEBUG
                formatter = logging.Formatter(
                    '%(asctime)s-%(levelname)s-%(funcName)15s-%(lineno)5d : %(message)s')
            else:
                loglevel = logging.INFO
                formatter = logging.Formatter(
                    '%(asctime)s-%(levelname)s : %(message)s')

            # logfile setting
            if options.log:
                logpath = options.log
            else:
                logpath = 'korok.log'

            # fh = logging.handlers.RotatingFileHandler(logpath, maxBytes = 1024*1024, backupCount = 5)
            logging.basicConfig(level=loglevel)
            fh = logging.FileHandler(logpath)
            ch = logging.StreamHandler(sys.stdout)

            fh.setFormatter(formatter)
            ch.setFormatter(formatter)

            self.Logger = logging.getLogger()
            self.Logger.addHandler(fh)
            self.Logger.addHandler(ch)

        except Exception as ex:
            print('Logging Initialization Failed')
            traceback.print_exc()

        try:
            # 解析 ini 文件
            self.ConParser = ConfigParser.ConfigParser()
            self.ConParser.read(self.ConfigFile)

        except Exception as ex:
            logging.error('Config File ' + self.ConfigFile + ' Error')
            logging.exception(ex)
            sys.exit()

    def Run(self):
        '''
        启动
        :return:
        '''

        success = 0
        failure = 0
        ret = 0

        sections = self.ConParser.sections()
        section = self.Options.section
        args = self.Args

        if section in sections:
            try:
                action = self.ConParser.get(section, 'action')
            except Exception as ex:
                ret = 2
                logging.error('Error: No Action definition ' + section)
                logging.exception(ex)

            if action == 'copy':
                if not self.Copy(section, args):
                    ret = 11

            elif action == 'execute':
                if not self.Execute(section):
                    ret = 12
            # clear
            elif action == 'clear':
                if not self.Clear(section, args):
                    ret = 13
            elif action == 'processmon':
                if not self.ProcessMon(section):
                    ret = 14
            elif action == 'service':
                if not self.Service(section, args):
                    ret = 15
            # backup
            elif action == 'archive':
                if not self.Zip(section):
                    ret = 16

            # backup by month
            elif action == 'archive_month':
                if not self.Zip_Month(section):
                    ret = 16

            else:
                logging.error('Error: No such Action ' + section)
                ret = 3

            logging.debug(section + ' ends')

        else:
            logging.info(" {}.{}".format(section,"is not setting"))
        return ret

    def Copy(self, section, args):

        # need parameter
        # src
        # dst
        # pattern
        # mtime
        # timestamp
        # reserve
        # recursive
        # compress

        try:
            src = self.ConParser.get(section, 'src')
            logging.info('Source Base Directory %s' % src)
        except Exception as ex:
            logging.error('No Source defined for Copy %s' % section)
            logging.exception(ex)
            return 0

        # confirm dst
        try:
            dest = self.ConParser.get(section, 'dst')
            logging.info('dest Directory %s' % dest)
        except Exception as ex:
            logging.error('No destination defined for Copy %s' % section)
            logging.exception(ex)
            return 0

        # confirm pattern
        try:
            patternlist = self.ConParser.get(section, 'pattern').split()
            logging.info('patternlist %s' % str(patternlist))
        except Exception as ex:
            logging.error('No pattern defined for Copy %s' % section)
            logging.exception(ex)
            return 0

        try:
            exclusionlist = self.ConParser.get(section, 'exclude').split()
            logging.info('exclusionlist %s' % str(exclusionlist))
        except Exception as ex:
            logging.info('No exclusion defined for Copy %s' % section)
            exclusionlist = None

        try:
            duration = str(self.ConParser.get(section, 'mtime'))
            delta = self.convert_to_time(duration)
            logging.info('delta %s' % str(delta))
            if delta is None:
                logging.error('Can not get time delta')
                return 0
        except Exception as ex:
            logging.warning(
                'No mtime defined for Copy %s, default value 0 used' %
                section)
            delta = 0

        try:
            timestamp = str(self.ConParser.get(section, 'timestamp'))
            logging.info('timestamp %s' % str(timestamp))
            if timestamp.upper() == 'NO' or timestamp.upper() == 'N':
                timestamp = ''
            else:
                dest = dest + '.' + self.ExecTime
        except Exception as ex:
            dest = dest + self.ExecTime
            logging.info('Un mark time stamp for Copy %s' % section)

        try:
            recursive = str(self.ConParser.get(section, 'recursive'))
            logging.info('recursive %s' % str(recursive))
            if recursive.upper() == 'YES' or recursive.upper() == 'Y':
                recursive = True
            else:
                recursive = False
        except Exception as ex:
            recursive = False
            logging.info('Non-recursive Mode for Copy %s' % section)

        try:
            compress = str(self.ConParser.get(section, 'compress'))
            logging.info('compress %s' % str(compress))
            if compress.upper() == 'YES' or compress.upper() == 'Y':
                compress = True
            else:
                compress = False
        except Exception as ex:
            compress = False
            logging.info('Non-compress Mode for Copy %s' % section)

        # begin copy handle
        copylist = []

        if recursive:
            # 递归处理
            try:
                '''
                for (root,dirs,files) in os.walk(src.decode('utf-8'),topdown=True):
                    for filename in files:
                        abssrc=os.path.join(root,filename)
                        mtime=os.stat(abssrc).st_mtime
                        if (self.NowTime-mtime) < delta:
                            continue
                        for pattern in patternlist:
                            #pattern=os.path.join(src,pattern)
                            if fnmatch.fnmatch(filename,pattern):
                                copylist.append(abssrc)
                                break
                #os.path.walk(src.decode('utf-8'),self.scan,(patternlist,src,delta,copylist))
                '''
                for member in os.listdir(src):
                    self.mycopywalk(
                        os.path.join(
                            src,
                            member),
                        patternlist,
                        exclusionlist,
                        delta,
                        copylist)
            except Exception as ex:
                logging.exception(ex)
        else:
            for pattern in patternlist:
                # pattern=os.path.join(src,pattern)
                # srcfiles=glob.glob(pattern)
                try:
                    srcfiles = os.listdir(src)
                except Exception as ex:
                    logging.exception(ex)

                for srcfile in srcfiles:
                    abssrc = os.path.join(src, srcfile)
                    mtime = os.stat(abssrc).st_mtime
                    if (self.NowTime - mtime) < delta:
                        continue
                    if not fnmatch.fnmatch(srcfile, pattern):
                        continue
                    # if os.path.islink(os.path.join(src,srcfile)):
                    #	continue
                    copylist.append(abssrc)

        if exclusionlist:
            for expattern in exclusionlist:
                for srcfile in copylist:
                    if fnmatch.fnmatch(os.path.basename(srcfile), expattern):
                        copylist.remove(srcfile)
                        # exclude.append(srcfile)

        logging.info('Copy List:')
        for copyfile in copylist:
            logging.info(copyfile)
        logging.info('Copy List Ends')

        if compress:
            try:
                destgzfile = tarfile.open(dest + '.tar.gz', 'w:gz')
                # destgzfile=tarfile.TarFile(name=dest+'.tar.gz',mode='w:gz',dereference=False)
                for srcfile in copylist:
                    destgzfile.add(srcfile, recursive=(not recursive))
                destgzfile.close()
            except Exception as ex:
                logging.exception(ex)

        else:

            if not os.path.exists(dest):
                os.makedirs(dest)
            for srcfile in copylist:
                try:
                    relpath = os.path.relpath(srcfile, src)
                    absdest = os.path.join(dest, relpath)
                    if os.path.isdir(srcfile):
                        if recursive:
                            shutil.copytree(srcfile, absdest, symlinks=True)
                            logging.info('copy directory %s' % srcfile)
                    elif os.path.isfile(srcfile):
                        shutil.copy2(srcfile, absdest)
                        logging.info('copy file %s' % srcfile)
                    elif os.path.islink(srcfile):
                        os.symlink(absdest, os.readlink(srcfile))
                except Exception as ex:
                    logging.exception(ex)
        return 1

    # zip by month

    def Zip_Month(self, section):
        '''
        :param section:
        # section need parameter
        # src  源目录
        # dst  目标目录
        # pattern 正则匹配
        # mtime   修改时间
        # timestamp bool 加时间标签
        # reserve  是否递归
        '''

        print('zip_by_month')
        _month = self.nowMonth()

        try:
            srclist = self.ConParser.get(section, 'src').split()
            _srclist = []
            for src in srclist:
                _srclist.append(os.path.join(src, _month))
            srclist = _srclist
            logging.debug('{:15}{:10}'.format('srcpath lst:', str(srclist)))

        except BaseException:
            print('No Source defined for Copy', section)
            self.PrintStack()
            return 0
        try:
            dest = self.ConParser.get(section, 'dst')
            dest = os.path.join(dest, _month)
            logging.debug('{:15}{:10}'.format('dstpath str:', str(dest)))
        except BaseException:
            print('No destination defined for Copy', section)
            self.PrintStack()
            return 0

        try:
            patternlist = self.ConParser.get(section, 'pattern').split('@@')
            # logging.debug('pattern lst' + str(patternlist))

            _patternlist = []
            for i in patternlist:
                _dirpath = os.path.dirname(i)
                _pattern = os.path.basename(i)
                _patternlist.append(os.path.join(_dirpath, _month, _pattern))

            patternlist = _patternlist

            logging.debug(
                '{:15}{:10}'.format(
                    'pattern lst:',
                    str(patternlist)))
        except BaseException:
            print('No pattern defined for Copy', section)
            self.PrintStack()
            return 0

        try:
            duration = str(self.ConParser.get(section, 'mtime'))
            # logging.debug('duration ' + str(duration))
            logging.debug('{:15}{:10}'.format('duration:', str(duration)))
        except BaseException:
            duration = None
            print('No mtime defined for Copy', section)

        try:
            timestamp = str(self.ConParser.get(section, 'timestamp'))
            if timestamp == 'yes' or timestamp == 'YES' or timestamp == 'y' or timestamp == 'Y':
                dest = os.path.join(
                    dest, self.ExecTime + '-' + self.HostNm + '.tar.gz')
                # dest = dest + self.ExecTime + '-' + self.HostNm + '.tar.gz'
            else:
                # dest = dest + '-' + self.HostNm + '.tar.gz'
                dest = os.path.join(dest, self.HostNm + '.tar.gz')
            # logging.debug('dest name will: ' + str(dest))
            logging.debug('{:15}{:10}'.format('dest will:', str(dest)))

        except BaseException:
            print('Unmark time stamp for Zip', section)

        try:
            reserve = str(self.ConParser.get(section, 'reserve'))
            if reserve == 'no' or reserve == 'NO' or reserve == 'n' or reserve == 'N':
                reserve = False
            else:
                reserve = True
            # logging.debug('reserve : ' + str(reserve))
            logging.debug('{:15}{:10}'.format('reserve:', str(reserve)))

        except BaseException:
            reserve = True
            print('Un mark time stamp for Copy', section)

        # get delta
        if duration:
            delta = self.convert_to_time(duration)
            if not delta:
                logging.error("Can not get time delta")
                print('Can not get time delta')
                return 0

        # create tar file
        try:
            if not os.path.exists(os.path.dirname(dest)):
                os.makedirs(os.path.dirname(dest))
            destgzfile = tarfile.open(dest, 'w:gz')
        except BaseException:
            print('Zip File creation failed for', dest)
            self.PrintStack()
            return 1

        # get file
        for pattern in patternlist:
            srcfiles = glob.glob(pattern)
            logging.debug('{:15}{:10}'.format('pattern file:', str(srcfiles)))
            for srcfile in srcfiles:
                cur_path = os.getcwd()
                os.chdir(os.path.dirname(srcfile))

                mtime = os.stat(srcfile).st_mtime
                if not (self.NowTime - mtime) > delta:
                    continue
                print('Zip from', srcfile, 'to', dest)
                logging.debug(
                    'Zip from {:15} srcfile {:10}'.format(
                        srcfile, dest))
                try:
                    srcfile = os.path.basename(srcfile)
                    if os.path.isfile(srcfile):
                        destgzfile.add(srcfile)
                        if not reserve:
                            os.remove(srcfile)
                    elif os.path.isdir(srcfile):
                        destgzfile.add(srcfile)
                        if not reserve:
                            shutil.rmtree(srcfile)
                except BaseException:
                    os.chdir(cur_path)
                    self.PrintStack()

        destgzfile.close()

    def Zip(self, section):
        '''
        :param section:
        # section need parameter
        # src  源目录
        # dst  目标目录
        # pattern 正则匹配
        # mtime   修改时间
        # timestamp bool 加时间标签
        # reserve  是否递归
        '''

        print('zip')
        try:
            srclist = self.ConParser.get(section, 'src').split('|')
            # logging.debug('srcpath lst:'+ str(srclist))
            logging.debug('{:15}{:10}'.format('srcpath lst:', str(srclist)))
        except BaseException:
            print('No Source defined for Copy', section)
            self.PrintStack()
            return 0
        try:
            dest = self.ConParser.get(section, 'dst')
            # logging.debug('dstpath str' + str(dest))
            logging.debug('{:15}{:10}'.format('dstpath str:', str(dest)))
        except BaseException:
            print('No destination defined for Copy', section)
            self.PrintStack()
            return 0

        try:
            patternlist = self.ConParser.get(section, 'pattern').split('@@')
            # logging.debug('pattern lst' + str(patternlist))
            logging.debug(
                '{:15}{:10}'.format(
                    'pattern lst:',
                    str(patternlist)))
        except BaseException:
            print('No pattern defined for Copy', section)
            self.PrintStack()
            return 0

        try:
            duration = str(self.ConParser.get(section, 'mtime'))
            # logging.debug('duration ' + str(duration))
            logging.debug('{:15}{:10}'.format('duration:', str(duration)))
        except BaseException:
            duration = None
            print('No mtime defined for Copy', section)

        try:
            timestamp = str(self.ConParser.get(section, 'timestamp'))
            if timestamp == 'yes' or timestamp == 'YES' or timestamp == 'y' or timestamp == 'Y':
                dest = dest + self.ExecTime + '-' + self.HostNm + '.tar.gz'
            else:
                dest = dest + '-' + self.HostNm + '.tar.gz'
            # logging.debug('dest name will: ' + str(dest))
            logging.debug('{:15}{:10}'.format('dest will:', str(dest)))

        except BaseException:
            print('Unmark time stamp for Zip', section)

        try:
            reserve = str(self.ConParser.get(section, 'reserve'))
            if reserve == 'no' or reserve == 'NO' or reserve == 'n' or reserve == 'N':
                reserve = False
            else:
                reserve = True
            # logging.debug('reserve : ' + str(reserve))
            logging.debug('{:15}{:10}'.format('reserve:', str(reserve)))

        except BaseException:
            reserve = True
            print('Un mark time stamp for Copy', section)

        # get delta
        if duration:
            delta = self.convert_to_time(duration)
            if not delta:
                logging.error("Can not get time delta")
                print('Can not get time delta')
                return 0

        # create tar file
        try:
            destgzfile = tarfile.open(dest, 'w:gz')
        except BaseException:
            print('Zip File creation failed for', dest)
            self.PrintStack()

        # get file
        for pattern in patternlist:
            srcfiles = glob.glob(pattern)
            logging.debug('{:15}{:10}'.format('pattern file:', str(srcfiles)))

            for srcfile in srcfiles:
                mtime = os.stat(srcfile).st_mtime
                if not (self.NowTime - mtime) > delta:
                    continue
                print('Zip from', srcfile, 'to', dest)
                logging.debug(
                    'Zip from {:15} srcfile {:10}'.format(
                        srcfile, dest))
                try:
                    print(os.getcwd())
                    if os.path.isfile(srcfile):
                        destgzfile.add(srcfile)
                        if not reserve:
                            os.remove(srcfile)
                    elif os.path.isdir(srcfile):
                        destgzfile.add(srcfile)
                        if not reserve:
                            shutil.rmtree(srcfile)
                except BaseException:
                    self.PrintStack()

    def mycopywalk(self, root, patternlist, exclusionlist, delta, copylist):
        logging.info('enter %s' % root)
        matchflag = False
        timeflag = False
        excludeflag = False

        mtime = os.stat(root).st_mtime
        if (self.NowTime - mtime) > delta:
            timeflag = True

        for pattern in patternlist:
            if fnmatch.fnmatch(root, pattern):
                matchflag = True
                break
        if exclusionlist:
            for exclude in exclusionlist:
                if fnmatch.fnmatch(os.path.basename(root), exclude):
                    excludeflag = True
                    break

        if timeflag and matchflag and (not excludeflag):
            copylist.append(root)

        if os.path.isdir(root) and not (os.path.islink(root)):
            if not excludeflag:
                logging.info('dir %s', root)
                for member in os.listdir(root):
                    self.mycopywalk(
                        os.path.join(
                            root,
                            member),
                        patternlist,
                        exclusionlist,
                        delta,
                        copylist)

    def scan(self, patternlist, src, delta, copylist, dirname, files):
        for filename in files:
            for pattern in patternlist:
                abssrc = os.path.join(dirname, filename)
                if fnmatch.fnmatch(abssrc, pattern):
                    # abssrc=os.path.join(dirname,filename)
                    relpath = os.path.relpath(abssrc, src)
                    try:
                        mtime = os.stat(abssrc).st_mtime
                        if (self.NowTime - mtime) < delta:
                            continue
                        copylist.append(abssrc)
                    except Exception as ex:
                        logging.exception(ex)
                        return 0
        return 1

    def Clear(self, section, args):

        # src
        # pattern
        # mtime
        # timestamp
        # recursive

        try:
            src = self.ConParser.get(section, 'src')
            logging.info('Source Base Directory %s' % src)
        except Exception as ex:
            logging.error('No srcdir defined for Clear %s' % section)
            logging.exception(ex)
            return 0

        try:
            patternlist = self.ConParser.get(section, 'pattern').split()
            print(patternlist)
        except Exception as ex:
            print('No pattern defined for Clear', section)
            self.printstack()
            return 0

        try:
            exclusionlist = self.ConParser.get(section, 'exclude').split()
        except Exception as ex:
            logging.info('No exclusion defined for Copy %s' % section)
            exclusionlist = None

        try:
            duration = str(self.ConParser.get(section, 'mtime'))
            delta = self.convert_to_time(duration)
            if delta is None:
                print('Can not get time delta')
                return 0
        except Exception as ex:
            print('No mtime defined for Clear', section)
            duration = 0

        try:
            recursive = str(self.ConParser.get(section, 'recursive'))
            if recursive.upper() == 'YES' or recursive.upper() == 'Y':
                recursive = True
            else:
                recursive = False
        except Exception as ex:
            recursive = False
            print('Non-recursive Mode', section)

        deletelist = []
        if recursive:
            try:
                for (
                        root,
                        dirs,
                        files) in os.walk(
                        src.decode('utf-8'),
                        topdown=False):
                    for filename in files:
                        abssrc = os.path.join(root, filename)
                        for pattern in patternlist:
                            if fnmatch.fnmatch(filename, pattern):
                                mtime = os.stat(abssrc).st_mtime
                                if (self.NowTime - mtime) < delta:
                                    break
                                deletelist.append(abssrc)

                    for dirname in dirs:
                        abssrc = os.path.join(root, dirname)
                        for pattern in patternlist:
                            if fnmatch.fnmatch(dirname, pattern):
                                mtime = os.stat(abssrc).st_mtime
                                if (self.NowTime - mtime) < delta:
                                    break
                                deletelist.append(abssrc)
            except Exception as ex:
                logging.exception(ex)

        else:
            for pattern in patternlist:
                try:
                    srcfiles = os.listdir(src)
                except Exception as ex:
                    logging.exception(ex)

                for srcfile in srcfiles:
                    abssrc = os.path.join(src, srcfile)
                    mtime = os.stat(abssrc).st_mtime
                    if (self.NowTime - mtime) < delta:
                        continue
                    if not fnmatch.fnmatch(srcfile, pattern):
                        continue
                    # if os.path.islink(os.path.join(src,srcfile)):
                    #	continue
                    deletelist.append(abssrc)

        if exclusionlist:
            for expattern in exclusionlist:
                for srcfile in deletelist:
                    if fnmatch.fnmatch(os.path.basename(srcfile), expattern):
                        deletelist.remove(srcfile)

        logging.info('Delete List:')
        for deletefile in deletelist:
            logging.info(deletefile)
            if os.path.isfile(deletefile) or os.path.islink(deletefile):
                try:
                    os.remove(deletefile)
                except Exception as ex:
                    logging.exception(ex)
            elif os.path.isdir(deletefile):
                try:
                    shutil.rmtree(deletefile)
                except Exception as ex:
                    logging.exception(ex)
        logging.info('Delete List Ends')

    def Execute(self, section):
        try:
            command = self.ConParser.get(section, 'command')
        except Exception as ex:
            print('No Command defined for Execution', section)
            self.printstack()
            return 0
        try:
            output = self.ConParser.get(section, 'output')
            print
            output
        except Exception as ex:
            output = None
            print('No Output defined forExecution', section)

        outfile = None

        if output:
            try:
                outfile = open(output, 'w')
                print('Open file', output, 'for execution output')
            except Exception as ex:
                print('Open file for execution output failed', section)
                return 0

        try:
            process = subprocess.Popen(command, stdout=outfile, shell=True)
        except Exception as ex:
            self.printstack()
            return 0
        return 1

    def ProcessMon(self, section):
        try:
            interval = float(self.ConParser.get(section, 'interval'))
        except Exception as ex:
            print('No interval defined for ProcessMon, use default value', section)
            self.printstack()
            interval = 5
        try:
            processkeyword = self.ConParser.get(section, 'processkeyword')
        except Exception as ex:
            print('No processkeyword defined for ProcessMon,exit', section)
            self.printstack()
            return 0

        try:
            command = self.ConParser.get(section, 'command')
        except Exception as ex:
            print('No command defined for ProcessMon', section)
            command = None
            self.printstack()

        try:
            outfile = self.ConParser.get(section, 'outfile')
        except Exception as ex:
            print('No outfile defined for ProcessMon, use default value', section)
            self.printstack()
            outfile = processkeyword + '.log'

        while True:
            (result, search) = self.find_process_by_cmd(processkeyword)
            if result:
                if not search:
                    print(
                        self.nowtime,
                        ' process ',
                        processkeyword,
                        'unsearched')
                    if not command:
                        print('No command defined for process to start')
                        time.sleep(interval)
                        continue
                    try:
                        process = subprocess.Popen(
                            command, stdout=open(
                                outfile, 'w'), shell=True)
                    except Exception as ex:
                        self.printstack()
                        print('Process starts Abnomal')

                else:
                    print(
                        self.nowtime,
                        ' process ',
                        processkeyword,
                        'searched')
            else:
                print('Module find_process_by_cmd Abnomal')
                sys.exit()
            time.sleep(interval)
        return 0

    def PrintStack(self):
        print("*** print_exc begins:")
        traceback.print_exc()
        print("*** print_exc ends ***")

    def Service(self, section, args):

        # startcommand
        # logfile
        # processes
        # listenports
        # connections
        # waittime
        # checkonly
        logging.debug('Enter Service')

        todoaction = args[0].split()[0].upper()
        actionlist = ['START', 'STOP', 'CHECK']
        check = {}
        if todoaction not in actionlist:
            logging.error(
                'No Action %s in Action List %s:' %
                (todoaction, actionlist))
            return 0

        try:
            startcommand = self.ConParser.get(section, 'start')
            logging.info('Startcommand: %s', startcommand)
        except Exception as ex:
            logging.error('No Startcommand defined for Service %s' % section)
            logging.exception(ex)
            return False

        try:
            stopcommand = self.ConParser.get(section, 'stop')
            logging.info('Stopcommand: %s', stopcommand)
        except Exception as ex:
            logging.error('No Stopcommand defined for Service %s' % section)
            logging.exception(ex)
            return False

        try:
            logfile = self.ConParser.get(section, 'logfile')
        except Exception as ex:
            logging.warning('No Log file defined for Service %s' % section)
            logfile = None

        try:
            processkeywords = self.ConParser.get(
                section, 'processes').split('|')
            check['processcheck'] = None
        except Exception as ex:
            logging.warning(
                'No Processes keywords defined for Service %s' %
                section)
            processkeywords = None

        try:
            listenports = self.ConParser.get(section, 'listenports').split('|')
            check['listenportcheck'] = None
        except Exception as ex:
            logging.warning('No Listenports defined for Service %s' % section)
            listenports = None

        try:
            connections = self.ConParser.get(section, 'connections').split('|')
            check['connectioncheck'] = None
        except Exception as ex:
            logging.warning('No Connnections defined for Service %s' % section)
            connections = None

        try:
            winservice = self.ConParser.get(section, 'winservice').split('|')
            check['winservice'] = None
        except Exception as ex:
            logging.warning('No Winservice defined for Service %s' % section)
            winservice = None

        try:
            waittime = self.ConParser.get(section, 'waittime')
        except Exception as ex:
            logging.warning(
                'No Waittime defined for Service %s, default value 1 second' %
                section)
            waittime = 1
        try:
            weblogiccheckcommand = self.ConParser.get(section, 'weblogiccheck')
            logging.info('Weblogic Check command %s' % weblogiccheckcommand)
            check['weblogiccheck'] = None
        except Exception as ex:
            logging.warning(
                'No Weblogic Check defined for Service %s' %
                section)
            weblogiccheckcommand = None

        if weblogiccheckcommand:
            try:
                weblogicnodes = self.ConParser.get(
                    section, 'weblogicnodes').split('|')
                logging.info('Weblogic Nodes to Check %s' % weblogicnodes)
            except Exception as ex:
                logging.error(
                    'No Weblogic Nodes defined for Service %s' %
                    section)
                weblogicnodes = None

        if todoaction == 'START':
            logging.info('To Start the Service %s' % section)
            if startcommand:
                executioncommand = startcommand
            else:
                logging.error('No Start Command,Exit')
                return False
        elif todoaction == 'STOP':
            logging.info('To Stop the Service %s' % section)
            if startcommand:
                executioncommand = stopcommand
            else:
                logging.error('No Stop Command,Exit')
                return False
        elif todoaction == 'CHECK':
            logging.info('To Check the Service %s' % section)
            executioncommand = None

        if executioncommand:
            '''
            if not platform.system() =='Windows':
                executioncommand=shlex.split(executioncommand)
                SHELL=False
            else:
                SHELL=True
            '''
            SHELL = True
            try:
                logging.info('Start Command: %s' % executioncommand)
                if logfile:
                    outfile = open(logfile, 'w+')
                    logging.info('Output to the Log file: %s' % logfile)
                    process = subprocess.Popen(
                        executioncommand, stdout=outfile, shell=SHELL)
                else:
                    process = subprocess.Popen(executioncommand, shell=SHELL)
                logging.info(
                    'The %s process\' pid :%s' %
                    (todoaction, process.pid))
            except Exception as ex:
                logging.exception(ex)
                return False
            time.sleep(float(waittime))

        if processkeywords:
            logging.info('Begin Process keyword Check')
            promatch = []
            for processkeyword in processkeywords:
                # index=processkeywords.index(processkeyword)
                # promatch[index]=False
                logging.info('The keywords to match: %s' % processkeyword)
                keywords = processkeyword.split(',')
                if not keywords:
                    continue
                try:
                    processnum = int(keywords[0])
                except Exception as ex:
                    logging.error('Start Module:processkeyword complie ERROR')
                    return False

                for keyword in keywords[1:]:
                    keywords[keywords.index(keyword)] = re.compile(keyword)
                resultpros = []
                try:
                    if platform.system() == 'Windows':
                        procheckcommand = 'tasklist /v'
                    else:
                        procheckcommand = 'ps -ef'
                    process = subprocess.Popen(
                        procheckcommand,
                        stdout=subprocess.PIPE,
                        shell=True,
                        universal_newlines=True)
                    output, unused_err = process.communicate()
                    retcode = process.poll()
                    ret = output.strip()
                    if retcode:
                        logging.warning('Process Check retcode: %s' % retcode)
                    logging.debug('The Process Check output:\n %s' % ret)
                    logging.debug('Process Check unused_err %s' % unused_err)
                    # ret = self.get_execution_result(procheckcommand)

                    for proline in ret.split('\n'):
                        matchedflag = True
                        for keyword in keywords[1:]:
                            if not keyword.search(proline):
                                matchedflag = False
                                break
                        if matchedflag:
                            # print proline,'matched'
                            resultpros.append(proline)
                    # print processnum
                    if len(resultpros) < processnum:
                        check['processcheck'] = False
                        logging.error(
                            'Processes Check Failed, Keyword %s Unmatched' %
                            processkeyword)
                    else:
                        check['processcheck'] = True
                        logging.info(
                            'Processes Check OK, Keyword %s matched, ' %
                            processkeyword)
                        logging.info('Matched Process content %s' % resultpros)
                except Exception as ex:
                    check['processcheck'] = False
                    logging.exception(ex)
            logging.info('End Process keyword Check')

        if listenports:
            logging.info('Begin Listen Ports Check')
            try:
                for ipport in listenports:
                    (ip, port) = ipport.split(':')
                    if not (ip and port):
                        continue
                    port = int(port)
                    logging.info('Try to connect %s:%s' % (ip, port))
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    conn_ret = sock.connect_ex((ip, port))
                    if conn_ret:
                        check['listenportcheck'] = False
                        logging.error(
                            'Listen Port Check ERROR:failed to connect to Listen_port %s:%s' %
                            (ip, port))
                        logging.error('The socket ERROR Code %s' % conn_ret)
                    else:
                        check['listenportcheck'] = True
                        logging.info(
                            'Listen Port Check OK:succeed to connect to Listen_port %s:%s' %
                            (ip, port))

            except Exception as ex:
                check['listenportcheck'] = False
                logging.error(
                    'Listen Port Check ERROR:failed to connect to Listen_port %s:%s' %
                    (ip, port))
                logging.exception(ex)
            finally:
                sock.close()
                logging.info('End Listen Ports Check')

        connectioncheck = True
        if connections:
            logging.info('Begin Connections Check')
            for ipports in connections:
                (connnum, ipport) = ipports.split(',')
                if not connnum:
                    continue
                connnum = int(connnum)
                (ip, port) = ipport.split(':')
                if not (ip and port):
                    continue
                port = int(port)
            try:
                if platform.system() == 'Windows':
                    logging.debug('The Check Command:')
                    # logging.debug('netstat -an | find \"ESTABLISHED\" | find \"'+ip+'\" | find \"'+str(port)+'\"')
                    command = 'netstat -an | find \"ESTABLISHED\" | find \"' + \
                        ip + '\" | find \"' + str(port) + '\"'
                else:
                    # logging.debug('netstat -an | grep ESTABLISHED | grep '+ip+' | grep '+str(port))
                    command = 'netstat -an | grep ESTABLISHED | grep ' + \
                        ip + ' | grep ' + str(port)
                logging.debug('The Check Command: %s' % command)

                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    shell=True,
                    universal_newlines=True)
                output, unused_err = process.communicate()
                retcode = process.poll()
                ret = output.strip()
                if retcode:
                    logging.warning('Check Process retcode: %s' % retcode)
                logging.debug('The Connection Check output:\n %s' % ret)
                logging.debug('Weblogic Check unused_err %s' % unused_err)
                if ret == '':
                    retlen = 0
                else:
                    retlen = len(ret.split('\n'))
                logging.debug('The Connnections established: %s,' % retlen)
                logging.debug(
                    'The Number of Connnections should be: %s,' %
                    connnum)
                if retlen < connnum:
                    check['connectioncheck'] = False
                    print(
                        'Only %i Connections connected to %s:%s' %
                        (retlen, ip, port))
                else:
                    check['connectioncheck'] = True
                    print(
                        'Connection Check OK: %i Connections connected to %s:%s' %
                        (retlen, ip, port))

            except Exception as ex:
                logging.error('Connections Check failed')
                check['connectioncheck'] = False
                logging.exception(ex)
            finally:
                logging.info('End Connections Check')

        if winservice:
            logging.info('Begin Windows Service Check')
            winservicecheckcommand = 'sc query'
            svrstate = {}
            check['winservice'] = True
            for service in winservice:
                svrstate[service] = None
                try:
                    process = subprocess.Popen(
                        winservicecheckcommand,
                        stdout=subprocess.PIPE,
                        shell=True,
                        universal_newlines=True)
                    output, unused_err = process.communicate()
                    retcode = process.poll()
                    ret = output.strip()
                    if retcode:
                        logging.warning(
                            'Windows Service Check Process retcode: %s' %
                            retcode)
                    logging.debug(
                        'The Windows Service Check output:\n %s' %
                        ret)
                    logging.debug(
                        'he Windows Service Check unused_err %s' %
                        unused_err)

                    svr = re.compile('SERVICE_NAME')
                    svrname = re.compile(service)

                    retlines = ret.split('\n')
                    for outline in retlines:
                        if svr.search(outline) and svrname.search(outline):
                            index = retlines.index(outline) + 3
                            stateline = retlines[index]
                            state = stateline.split(':')[1].split()[1].strip()
                            # check['winservice']=True
                            svrstate[service] = state
                            logging.info(
                                'The Service %s State :%s' %
                                (service, state))
                            break

                    if not svrstate[service] == 'RUNNING':
                        check['winservice'] = False

                except Exception as ex:
                    logging.error('Windows Service %s Check failed' % service)
                    # check['winservice'] = False
                    logging.exception(ex)
            logging.debug('Windows Service Check %s' % svrstate)

        if weblogiccheckcommand:
            try:
                process = subprocess.Popen(
                    weblogiccheckcommand,
                    stdout=subprocess.PIPE,
                    shell=True,
                    universal_newlines=True)
                output, unused_err = process.communicate()
                retcode = process.poll()
                ret = output.strip()
                if retcode:
                    logging.warning('Check Process retcode: %s' % retcode)
                logging.debug('Weblogic Check Output :\n %s' % output)
                logging.debug('Weblogic Check unused_err %s' % unused_err)

                if weblogicnodes:
                    nodestatus = {}
                    logging.debug('Weblogic Nodes: %s' % weblogicnodes)
                    for node in weblogicnodes:
                        nodestatus[node] = None
                        keyword = 'Current state of \'' + node + '\''
                        keyword = re.compile(keyword)
                        for line in ret.split('\n'):
                            if keyword.search(line):
                                logging.debug('Matched line %s ' % line)
                                status = line.split(':')[1].strip()
                                logging.debug('Node status %s' % status)
                                nodestatus[node] = status
                    logging.info('The Weblogic Nodes Status %s' % nodestatus)

                    if todoaction in ['START', 'CHECK']:
                        check['weblogiccheck'] = True
                        for node in weblogicnodes:
                            if not (nodestatus[node] == 'RUNNING'):
                                check['weblogiccheck'] = False
                                break

                    elif todoaction in ['STOP']:
                        check['weblogiccheck'] = False
                        for node in weblogicnodes:
                            if not (
                                    nodestatus[node] == 'SHUTDOWN' or nodestatus[node] is None):
                                check['weblogiccheck'] = True
                                break

                else:
                    check['weblogiccheck'] = False
                    logging.error('Weblogic Nodes not defined')

            except Exception as ex:
                check['weblogiccheck'] = False
                logging.exception(ex)
            finally:
                logging.info('End Weblogic Check')

        logging.info('The Total check result: %s' % check)
        if todoaction in ['START', 'CHECK']:
            checkret = True
            for checkterm in check.keys():
                checkret = checkret and check[checkterm]

        elif todoaction in ['STOP']:
            checkret = False
            for checkterm in check.keys():
                checkret = checkret or check[checkterm]
            checkret = not checkret

        return checkret

    def get_execution_result(self, command):
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            shell=True,
            universal_newlines=True)
        output, unused_err = process.communicate()
        retcode = process.poll()
        if retcode:
            logging.warning('execution retcode: %s' % retcode)
        ret = output.strip()
        logging.debug('execution retcode: %s' % retcode)
        logging.debug('execution Output :\n %s' % output)
        logging.debug('execution unused_err %s' % unused_err)
        return ret

    def find_process_by_cmd(self, cmdkeyword):
        # print(platform.architecture())
        # print(platform.platform())
        # print(platform.system())
        plist = []
        if platform.system() == 'Windows':
            try:
                psutil = __import__('psutil')
                processlist = psutil.get_pid_list()
            except Exception as ex:
                self.printstack()
                return (False, plist)

            # print processlist
            for process in processlist:

                try:
                    pro = psutil.Process(process)
                except Exception as ex:
                    print(self.nowtime, 'Abnormal:No process of', process)
                    self.printstack()
                    continue

                p = re.compile(cmdkeyword)
                for cmd in pro.cmdline:
                    if p.search(cmd):
                        print(cmdkeyword, 'Matched')
                        plist.append((process, pro.name))
        else:
            try:
                process = subprocess.Popen(
                    'ps -ef', stdout=subprocess.PIPE, shell=True)
                process.stdout.readlines()
            except Exception as ex:
                pass

        return (True, plist)

    def printstack(self):
        print("*** print_exc begins:")
        traceback.print_exc(file=sys.stdout)
        print("*** print_exc ends ***")

    # 1-0-0-11
    # day-hour-min-sec
    # return seconds
    def convert_to_time(self, duration):
        duration = duration.split('-')
        if not len(duration) == 4:
            print('duration format ERROR')
            return None
        try:
            days = int(duration[0])
            hours = int(duration[1])
            minutes = int(duration[2])
            seconds = int(duration[3])
            duration = [days, hours, minutes, seconds]
            # print duration
            delta = ((days * 24 + hours) * 60 + minutes) * 60 + seconds
        except Exception as ex:
            print('duration format ERROR')
            self.printstack()
            return None
        # print delta
        return delta

    def nowtime(self):
        return time.strftime('%Y%m%d-%H%M%S', time.localtime(time.time()))

    def nowMonth(self):
        return time.strftime('%Y%m', time.localtime(time.time()))


def ParseArgs():
    '''
    参数解析
    :return: option args
    '''
    parser = optparse.OptionParser()
    parser.add_option(
        "-f",
        "--file",
        type="string",
        dest="filename",
        help="Specify the Config file",
        default="setting.ini")
    parser.add_option(
        "-n",
        "--node",
        type="string",
        dest="node",
        help="Specify the the name of Server/Node")
    parser.add_option(
        "-s",
        "--section",
        type="string",
        dest="section",
        help="Specify the Section to Run",
        default="archive-month-test")
    parser.add_option(
        "-l",
        "--log",
        type="string",
        dest="log",
        help="Specify the log path")
    parser.add_option(
        "-d",
        action="store_true",
        default='True',
        dest="debug",
        help="Indicate whether to log debug info")
    (options, args) = parser.parse_args()

    if not options.filename:
        options.error(
            'Error : Config file Missing. Use -f or --file to specify the config file')

    print('*' * 50)
    print(options)
    print('*' * 50)
    return options, args


def main():
    options,args = ParseArgs()
    MyOper = Coper(options, args)
    ret = MyOper.Run()
    sys.exit(ret)

if __name__ == '__main__':
    main()

