#!/usr/bin/python
# -*- coding: utf-8 -*-

# ------------------------------------------------------------
# Filename:    zabbix.py
# Revision:    1.1
# CreateDate:  20/12/2016
# Author:      mingjianyong
# Description:
#
# -------------------------------------------------------
# Version 1.1
# The first one
# -------------------------------------------------------

import json
import urllib2
from urllib2 import URLError,HTTPError
import logging
import argparse
import sys

zabbix_zyc = "http://*/api_jsonrpc.php"
zabbix_rhtx = "http://*/zabbix/api_jsonrpc.php"
header = {"Content-Type":"application/json"}

class auto_zabbix:
    def __init__(self):
        self.type=""
        self.url=""

    def auth(self,url):
        user=""
        pwd=""
        if self.type=='RHTX':
            user="ZABBIXAPI"
            pwd="ZABBIXAPI"
        elif self.type=='ZYC':
            user="ZABBIXAPI"
            pwd = "ZABBIXAPI"
        data = json.dumps(
            {
                "jsonrpc": "2.0",
                "method": "user.login",
                "params": {
                     "user": user,
                     "password": pwd
                },
                "id": "1"
            }
        )
        request = urllib2.Request(url,data)
        for key in header:
            request.add_header(key,header[key])
        try:
            result = urllib2.urlopen(request)
        except HTTPError as e:
            pass
            #logger.error("The server couldn\'t fulfill the request,Error code:",e.code)
        except URLError as e:
            pass
            #logger.error("we failed to reach a server.Reason:",e.reason)
        else:
            response = json.loads(result.read())
            result.close()
            if 'result' in response:
                return response['result']
            else:
                pass
                #logger.error(response['error']['data'])
    def do_request(self,method,params,authid,url):
        data = json.dumps(
            {
                "jsonrpc": "2.0",
                "method": method,
                "params": params or {},
                "auth": authid,
                "id": 0
            }
        )
        request = urllib2.Request(url,data)
        for key in header:
            request.add_header(key,header[key])
        try:
            result = urllib2.urlopen(request)
        except HTTPError as e:
            pass
            #logger.error("The server couldn\'t fulfill the request,Error code:",e.code)
        except URLError as e:
            pass
            #logger.error("we failed to reach a server.Reason:",e.reason)
        else:
            response = json.loads(result.read())
            result.close()
            return response
    def get(self,host,url):
        authid =self.auth(url)
        params = {
            "output":["name","host",'hostid'],
            "filter":{
                "name":[
                    host
                ]
            }
        }
        try:
            response =self.do_request('host.get',params,authid,url)
            if 'result' in response:
                return response['result'][0]['hostid']
            else:
                print response['error']
                exit(0)
        except Exception as e:
            print response
            exit(0)

    def addTempletes(self,host,tid,url):
        authid =self.auth(url)
        hostid=self.get(host,url)
        params= {
                "hostid": hostid,
                "templates":
                    tid

        }
        try:
            response =self.do_request('host.update',params,authid,url)
            if 'result' in response:
                print "add Templates success"
            else:
                print response['error']
                exit(0)
        except Exception as e:
            print response
            exit(0)
    def clearTempletes(self,host,tid,url):
        authid =self.auth(url)
        hostid=self.get(host,url)
        params= {
                "hostid": "10126",
                "templates_clear": tid
        }
        try:
            response =self.do_request('host.update',params,authid,url)
            if 'result' in response:
                print "clear Templates success"
            else:
                print response['error']
                exit(0)
        except Exception as e:
            print response
            exit(0)
if __name__=='__main__':

    parser = argparse.ArgumentParser(description='zabbix template api ',usage='%(prog)s [options]')
    parser.add_argument('-A','--add-Templates',dest='addtem',nargs=3,metavar=('idc','host','tid'),help='add templates')
    parser.add_argument('-C','--clear-Templates',dest='clear',nargs=3,metavar=('idc','host','tid'),help='clear templates')
    if len(sys.argv)==1:
        print parser.print_help()
    else:
        args = parser.parse_args()
        zabbix = auto_zabbix()
        if args.addtem:
            if args.addtem[0]=='RHTX':
                zabbix.url=zabbix_rhtx
            elif args.addtem[0]=='ZYC':
                zabbix.url=zabbix_zyc
            else:
                print "input error"
            ip = args.addtem[1]
            tid = args.addtem[2]
            tids = tid.split(",")
            tid_list=list()
            for t in tids:
                add=dict()
                add["templateid"]=t
                tid_list.append(add)
            zabbix.addTempletes(ip,tid_list,zabbix.url)
        if args.clear:
            if args.addtem[0]=='RHTX':
                zabbix.url=zabbix_rhtx
            elif args.addtem[0]=='ZYC':
                zabbix.url=zabbix_zyc
            else:
                print "input error"
            ip = args.addtem[1]
            tid = args.addtem[2]
            tids = tid.split(",")
            tid_list=list()
            for t in tids:
                add=dict()
                add["templateid"]=t
                tid_list.append(add)
            zabbix.clearTempletes(ip,tid_list,zabbix.url)
"""
1、新增模板
参数：IP，模板id列表，zabbixurl
2、清楚主机模板
参数：IP，模板id列表，zabbixurl
"""


