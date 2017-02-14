#!/usr/bin/python
# -*- coding: utf-8 -*-

# ------------------------------------------------------------
# Filename:    zabbix.py
# Revision:    1.1
# CreateDate:  17/10/2016
# Author:      mingjianyong
# Description: Automatic add zabbix host;
#              Automatic  check zabbix_agentd.conf file and modify;
# ------------------------------------------------------------
# Version 1.1
# The first one
# ------------------------------------------------------------

import json
import urllib2
import commands
from urllib2 import URLError,HTTPError
import uuid
import argparse
import cx_Oracle
import sys
import time
import logging
import logging.handlers
import os
import MySQLdb
import socket
os.environ['NLS_LANG'] = 'SIMPLIFIED CHINESE_CHINA.UTF8'


zabbix_zyc = "http://*/api_jsonrpc.php"
zabbix_rhtx = "http://8/zabbix/api_jsonrpc.php"
header = {"Content-Type":"application/json"}

mysqlConn = {"host":"*","user":"*","passwd":"*","db":"*","port":3306}
conn = MySQLdb.connect(host=mysqlConn["host"],user=mysqlConn["user"],passwd=mysqlConn["passwd"],db=mysqlConn["db"],port=mysqlConn["port"],charset="utf8")
cur = conn.cursor()


"""用户认证,取得一个SESSIONID"""
class auto_zabbix:
    def __init__(self):
        self.type=""
        self.hostname=""
        self.tag=""

    def auth(self,url):
        user=""
        pwd=""
        if self.type=='A':
            user="ZABBIXAPI"
            pwd="123"
        elif self.type=='B':
            user="ZABBIXAPI"
            pwd = "123"
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
            logger.error("The server couldn\'t fulfill the request,Error code:",e.code)
        except URLError as e:
            logger.error("we failed to reach a server.Reason:",e.reason)
        else:
            response = json.loads(result.read())
            result.close()
            if 'result' in response:
                return response['result']
            else:
                logger.error(response['error']['data'])
    #执行post请求
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
            logger.error("The server couldn\'t fulfill the request,Error code:",e.code)
        except URLError as e:
            logger.error("we failed to reach a server.Reason:",e.reason)
        else:
            response = json.loads(result.read())
            result.close()
            return response

    #判断主机是否存在
    def isexist(self,host,url,type):
        self.type=type
        authid = self.auth(url)
        params = {
            "name": host
        }
        response = self.do_request('host.exists',params,authid,url)
        if 'result' in response:
            if response['result']==True:
                return True
            else:
                return False
        else:
            logger.error('%s not exists' %host)
            return False

    #获取主机的主机名信息
    def get(self,host,url):
        authid =self.auth(url)
        """
        params = {
            "output":["name","host"],
            "filter":{
                "name":[
                    host
                ]
            }
        }
        """
        params = {
            "output":"extend",
            "filter":{
                "ip":[host]
            },
            "selectHosts":[
                "host",
                "proxy_hostid"
            ]
        }
        response =self.do_request('host.get',params,authid,url)
        return response

    #检测zabbix_agentd主机名是否正常
    def check_hostname(self,host,url):
        sta,val = commands.getstatusoutput("ansible %s -m shell -a 'hostname' -u tyyw03" %host)
        if sta == 0 and val!="No hosts matched":
            response = self.get(host,url)
            try:
                if response['result'][0]['host'] == val.split('\n')[1]:
                    self.hostname=val.split('\n')[1]
                    return True
                else:
                    logger.error('%s hostname incorrect' %host)
                    return self.modify_hostname(url,host)
            except Exception as e:
                logger.error("get %s error or ansible get hostname error:%s"%(host,e))
                return self.modify_hostname(url,host)
        else:
            print "ansible:No hosts matched"
            exit(0)
    #检测主机某一端口是否正常
    def check_port(self,host,proxy_ip):
        sta_port,val_port=commands.getstatusoutput("ansible %s -m script -a '/opt/aspire/autoweb/script/zabbix/bin/check_port.py %s 10051' -u tyyw03 -s"%(host,proxy_ip))
        if sta_port == 0 and "port_success" in val_port:
            return True
        else:
            logger.error("proxy %s:10051 unable to connect"%(proxy_ip))
            return False
    #检车主机上的zabbix_agentd进程是否正常
    def check_process(self,host):
        sta,val = commands.getstatusoutput("ansible %s -m shell -a 'ps -ef | grep zabbix_agentd | grep -Ev grep' -u tyyw03 -s" %host)
        if sta == 0:
            val_list = val.split('\n')
            val_list.pop(0)
            if len(val_list) > 0:
                return True
            else:
                logger.error('%s zabbix_agent process exception! ' %host)
                return False
        else:
            logger.error('%s zabbix_agentd process exception' %host)
            return False
    def restart_process(self,host):
        """
        sta,val = commands.getstatusoutput("ansible %s -m shell -a 'service zabbix_agentd start' -u tyyw03 -s" %host)
        if sta == 0:
            if 'success' in val:
                pass
            else:
                logger.error('%s zabbix_agentd service start success'%host)
        else:
            logger.error('%s zabbix_agentd service start success'%host)
        """
        sta,val = commands.getstatusoutput('ansible %s -m raw -a "ps -ef |grep zabbix_agentd|grep -i zabbix_agentd|grep -v grep|awk \'{print \\"kill -9 \\" \$2}\'|sh" -u tyyw03 -s'%host)
        sta1,val1 = commands.getstatusoutput("ansible %s -m shell -a '/opt/aspire/product/zabbix/sbin/zabbix_agentd -c /opt/aspire/product/zabbix/conf/zabbix_agentd.conf' -u tyyw03 -s" %host)
        if sta1==0:
            return True
        else:
            logger.error('%s zabbix_agentd service restart failed'%host)
            print "zabbix_agentd service restart failed"
            return False


    #检查zabbox_agent主机配置文件是否正确
    def check_conf(self,host,servertype):
        sta,val = commands.getstatusoutput("ansible %s -m shell -a 'grep \"^ServerActive\" /opt/aspire/product/zabbix/conf/zabbix_agentd.conf' -u tyyw03 -s" %host)
        sta1,val1 = commands.getstatusoutput("ansible %s -m shell -a 'grep \"^Server=\" /opt/aspire/product/zabbix/conf/zabbix_agentd.conf' -u tyyw03 -s" %host)
        sta2,val2 = commands.getstatusoutput("ansible %s -m shell -a 'grep -E \"^AllowRoot=1\" /opt/aspire/product/zabbix/conf/zabbix_agentd.conf' -u tyyw03 -s" %host)
        if sta == 0 and sta1 == 0 and val!="No hosts matched":
            try:
                proxy = val.split('\n')[1].split('=')[1]
                proxy_all=""
                conf_proxy_hostid=""
                url=""
                if servertype == 'RHTX':
                    proxy_all = self.get_rhtx_proxy()
                    url=zabbix_rhtx
                elif servertype == 'ZYC':
                    proxy_all = self.get_zyc_proxy()
                    url=zabbix_zyc
                proxy_ip_list=list()
                for i in proxy_all:
                    if i[3]==proxy:
                        conf_proxy_hostid=i[2]
                    proxy_ip_list.append(i[3])
                #拼接上MM的代理机-start
                proxy_ip_list.append("192.168.93.205")
                #拼接上MM的代理机-end
                response = self.get(host,url)
                proxy_hostid = response['result'][0]['proxy_hostid']
                server_list = val1.split('\n')[1].split('=')[1].split(',')
                if proxy in proxy_ip_list and 'success' in val2 and proxy_hostid==conf_proxy_hostid:
                    #检测目标机器与代理机10051端口是否正常连通-START
                    if not self.check_port(host,proxy):
                        return self.modify_conf(host)
                    #end
                    if servertype == 'RHTX':
                        proxy_ip_list.append("10.1.220.43")
                    elif servertype == 'ZYC':
                        proxy_ip_list.append("10.153.1.21")
                    proxy_ip_list.append("127.0.0.1")
                    flag=True
                    for server in server_list:
                        if server not in proxy_ip_list:
                            flag = False
                            break
                    if flag:
                        return True
                    else:
                        logger.error("%s zabbix_agentd.conf Server Configuration incorrect" %host)
                        return self.modify_conf(host)
                else:
                    logger.error('%s Configuration Error:  Init ServerActive error in zabbix_agent.conf file' %host)
                    return self.modify_conf(host)
            except Exception as e:
                logger.error('%s get zabbix_agentd.conf Server or ServerActive error:%s' %(host,e))

                return self.modify_conf(host)
        else:
            if val=="No hosts matched":
                print "ansible:%s"%val
                exit(0)
            if self.install(host):
                return self.check_conf(host,servertype)
            else:
                logger.error('%s zabbix_agentd install failed'%host)
                return False

    def check(self,host,url):
        re0 = self.check_hostname(host,url)
        re1 = self.check_conf(host,self.type)
        re2 = self.check_process(host)
        re3 =True
        if not re2:
            self.restart_process(host)
        else:
            pass
        if re0 and re1 and re2 and re3:
            return True
        else:
            return False

    def install(self,ip):
        val = commands.getstatusoutput("/opt/aspire/autoweb/script/zabbix/bin/zabbixInstall.sh %s"%ip)
        val_str = val[1]
        if 'unreachable=0' in val_str and 'failed=0' in val_str:
            return True
        else:
            logger.error("%s zabbix_agentd install fail"%ip)
            print ("%s zabbix_agentd install fail"%ip)
            return False

    def modify_hostname(self,url,host):
        authid= self.auth(url)
        response=self.get(host,url)
        try:
            sta,val = commands.getstatusoutput("ansible %s -m shell -a 'hostname' -u tyyw03" %host)
            hostid=response['result'][0]['hostid']
            params = {
                "hostid":hostid,
                "host":val.split('\n')[1]
            }
            response = self.do_request('host.update',params,authid,url)
            if 'result' in response:
                return True
            elif 'error' in response:
                print response['error']['data']
                return False
        except Exception as e:
            logger.error("HOST:%s\t hostid:%s hostname modify failed:%e"%(host,hostid,e))
            return False

    def modify_conf(self,host):
        sta,val = commands.getstatusoutput("ansible %s -m shell -a 'grep \"^ServerActive\" /opt/aspire/product/zabbix/conf/zabbix_agentd.conf' -u tyyw03 -s" %host)
        try:
            if sta == 0:
                proxy=None
                url=""
                if self.type=='RHTX':
                    proxy = self.get_rhtx_proxy()
                    url=zabbix_rhtx
                elif self.type=='ZYC':
                    proxy = self.get_zyc_proxy()
                    url=zabbix_zyc
                elif self.tag=='MM':
                    proxy = self.get_mm_proxy()
                    url=zabbix_zyc
                proxy_list=list()
                for i in proxy:
                    proxy_list.append(i[3])
                if self.type == 'RHTX':
                    proxy_list.append("10.1.220.43")
                elif self.type == 'ZYC':
                    proxy_list.append("10.153.1.21")
                if self.tag=='MM':
                    proxy_list.append("192.168.93.205")
                proxy_list.append("127.0.0.1")
                proxyString = ",".join(proxy_list)

                #检测目标机器与代理机10051端口是否正常连通-START
                result=self.get_connect_proxy(host,proxy)
                if result is None:
                    print "No agents are available!"
                    return False
                #检测代理机10051端口是否正常-END

                status,value = commands.getstatusoutput("ansible %s -m shell -a 'sed -i \"s/^ServerActive=.*/ServerActive=%s/g\" /opt/aspire/product/zabbix/conf/zabbix_agentd.conf' -u tyyw03 -s" %(host,result[3]))
                sta_server,val_server = commands.getstatusoutput("ansible %s -m shell -a 'sed -i \"s/^Server=.*/Server=%s/g\" /opt/aspire/product/zabbix/conf/zabbix_agentd.conf' -u tyyw03 -s" %(host,proxyString))
                sta_allow,val_allow = commands.getstatusoutput("ansible %s -m shell -a 'grep -E \"^AllowRoot=0|^AllowRoot=1\" /opt/aspire/product/zabbix/conf/zabbix_agentd.conf' -u tyyw03 -s" %host)
                if 'success'in val_allow:
                    commands.getstatusoutput("ansible %s -m shell -a 'sed -i \"s/^AllowRoot=.*/AllowRoot=1/g\" /opt/aspire/product/zabbix/conf/zabbix_agentd.conf' -u tyyw03 -s" %host)
                else:
                    commands.getstatusoutput("ansible %s -m shell -a 'sed -i \"/AllowRoot=0/a\AllowRoot=1\" /opt/aspire/product/zabbix/conf/zabbix_agentd.conf' -u tyyw03 -s" %host)
                #修改配置文件Hostname项，和HostnameItem项

                sta_hname,val_hname = commands.getstatusoutput("ansible %s -m shell -a 'grep -E \"^Hostname=*|^HostnameItem=*\" /opt/aspire/product/zabbix/conf/zabbix_agentd.conf' -u tyyw03 -s" %host)
                if 'HostnameItem' in val_hname and 'Hostname' in val_hname:
                    commands.getstatusoutput("ansible %s -m shell -a 'sed -i \"s/^Hostname=/#Hostname=/g\" /opt/aspire/product/zabbix/conf/zabbix_agentd.conf' -u tyyw03 -s" %host)
                    commands.getstatusoutput("ansible %s -m shell -a 'sed -i \"s/^HostnameItem=.*/HostnameItem=system.hostname/g\" /opt/aspire/product/zabbix/conf/zabbix_agentd.conf' -u tyyw03 -s" %host)
                elif 'Hostname' in val_hname and 'HostnameItem' not in val_hname:
                    commands.getstatusoutput("ansible %s -m shell -a 'sed -i \"s/^Hostname=/#Hostname=/g\" /opt/aspire/product/zabbix/conf/zabbix_agentd.conf' -u tyyw03 -s" %host)
                    commands.getstatusoutput("ansible %s -m shell -a 'sed -i \"/#HostnameItem=/a\HostnameItem=system.hostname\" /opt/aspire/product/zabbix/conf/zabbix_agentd.conf' -u tyyw03 -s" %host)
                else:
                    commands.getstatusoutput("ansible %s -m shell -a 'sed -i \"/#HostnameItem=/a\HostnameItem=system.hostname\" /opt/aspire/product/zabbix/conf/zabbix_agentd.conf' -u tyyw03 -s" %host)

                if status==0 and 'success' in value and sta_server == 0 and 'success' in val_server:
                    #zabbix_agent.conf配置文件修改成功，重启zabbix_agent进程
                    #status1, value1 = commands.getstatusoutput("ansible %s -m shell -a 'service zabbix_agentd restart' -u tyyw03 -s" %host)
                    status1=self.restart_process(host)

                    if status1:

                        return self.update_host_proxy(host,result[2],url)
                    else:
                        return False
                else:
                    logger.error('%s zabbix_agent.conf modify error' %host)
                    return False
            else:
                logger.error("%s zabbix_agentd.conf error" %host)
                return False
        except Exception as e:
            print e
            logger.error("%s modify error:%s" %(host,e))
            return False

    def delete_host(self,url,host):
        authid = self.auth(url)
        try:
            response = self.get(host,url)
            hostid = response['result'][0]['hostid']
            params = [
                {"hostid": hostid}
            ]
            response = self.do_request('host.delete',params,authid,url)
            hostids = response['result']['hostids']
            if hostid:
                print "Delete %s successed" %hostid
            else :
                logger.error("Delete %s failed" %hostid)
        except Exception as e:
            logger.error("%s not exist" %host)

    #新增主机，并修改配置文件
    def add(self,url, host, groupid, tempid, proxy):
        #添加成功检查配置文件
        sta,val = commands.getstatusoutput("ansible %s -m shell -a 'grep \"^ServerActive\" /opt/aspire/product/zabbix/conf/zabbix_agentd.conf' -u tyyw03 -s" %host)
        if sta == 0 and val!="No hosts matched":
            if 'ServerActive' in val:
                proxy_list=list()
                for i in proxy:
                    proxy_list.append(i[3])
                if self.type == 'RHTX':
                    proxy_list.append("10.1.220.43")
                elif self.type == 'ZYC':
                    proxy_list.append("10.153.1.21")
                proxy_list.append("127.0.0.1")
                proxyString = ",".join(proxy_list)
                #检测代理机10051端口是否正常-START
                result=self.get_connect_proxy(host,proxy)
                if result is None:
                    print "No agents are available!"
                    return False
                #检测代理机10051端口是否正常-END
                status,value = commands.getstatusoutput("ansible %s -m shell -a 'sed -i \"s/^ServerActive=.*/ServerActive=%s/g\" /opt/aspire/product/zabbix/conf/zabbix_agentd.conf' -u tyyw03 -s" %(host,result[3]))
                sta_server,val_server = commands.getstatusoutput("ansible %s -m shell -a 'sed -i \"s/^Server=.*/Server=%s/g\" /opt/aspire/product/zabbix/conf/zabbix_agentd.conf' -u tyyw03 -s" %(host,proxyString))
                sta_allow,val_allow = commands.getstatusoutput("ansible %s -m shell -a 'grep -E \"^AllowRoot=0|^AllowRoot=1\" /opt/aspire/product/zabbix/conf/zabbix_agentd.conf' -u tyyw03 -s" %host)
                if 'success'in val_allow:
                    commands.getstatusoutput("ansible %s -m shell -a 'sed -i \"s/^AllowRoot=.*/AllowRoot=1/g\" /opt/aspire/product/zabbix/conf/zabbix_agentd.conf' -u tyyw03 -s" %host)
                else:
                    commands.getstatusoutput("ansible %s -m shell -a 'sed -i \"/AllowRoot=0/a\AllowRoot=1\" /opt/aspire/product/zabbix/conf/zabbix_agentd.conf' -u tyyw03 -s" %host)
                sta_hname,val_hname = commands.getstatusoutput("ansible %s -m shell -a 'grep -E \"^Hostname=*|^HostnameItem=*\" /opt/aspire/product/zabbix/conf/zabbix_agentd.conf' -u tyyw03 -s" %host)
                if 'HostnameItem' in val_hname and 'Hostname' in val_hname:
                    commands.getstatusoutput("ansible %s -m shell -a 'sed -i \"s/^Hostname=/#Hostname=/g\" /opt/aspire/product/zabbix/conf/zabbix_agentd.conf' -u tyyw03 -s" %host)
                    commands.getstatusoutput("ansible %s -m shell -a 'sed -i \"s/^HostnameItem=.*/HostnameItem=system.hostname/g\" /opt/aspire/product/zabbix/conf/zabbix_agentd.conf' -u tyyw03 -s" %host)
                elif 'Hostname' in val_hname and 'HostnameItem' not in val_hname:
                    commands.getstatusoutput("ansible %s -m shell -a 'sed -i \"s/^Hostname=/#Hostname=/g\" /opt/aspire/product/zabbix/conf/zabbix_agentd.conf' -u tyyw03 -s" %host)
                    commands.getstatusoutput("ansible %s -m shell -a 'sed -i \"/#HostnameItem=/a\HostnameItem=system.hostname\" /opt/aspire/product/zabbix/conf/zabbix_agentd.conf' -u tyyw03 -s" %host)
                else:
                    commands.getstatusoutput("ansible %s -m shell -a 'sed -i \"/#HostnameItem=/a\HostnameItem=system.hostname\" /opt/aspire/product/zabbix/conf/zabbix_agentd.conf' -u tyyw03 -s" %host)
                if status==0 and 'success' in value and sta_server == 0 and 'success' in val_server:
                    #zabbix_agent.conf配置文件修改成功，重启zabbix_agent进程
                    #status1, value1 = commands.getstatusoutput("ansible %s -m shell -a 'service zabbix_agentd restart' -u tyyw03 -s" %host)
                    status1=self.restart_process(host)
                    if status1:
                        return self.add_host(url,host,groupid,tempid,result[2])
                    else:

                        return False
                else:
                    logger.error('%s zabbix_agent.conf modify error' %host)
                    return False
            else:
                logger.error("%s zabbix_agent install error! please full install" %host)
                return False
        else:
            print "ansible:%s"%val
            logger.error("%s zabbix add failed!" %host)
            exit(0)


    def add_host(self,url,host,groupid,tempid,proxy_hostid):
        authid = self.auth(url)
        sta,val = commands.getstatusoutput("ansible %s -m shell -a 'hostname' -u tyyw03" %host)
        params = {
            "host":val.split('\n')[1],
            "name":host,
            "proxy_hostid":proxy_hostid,
            "interfaces": [
                {
                    "type": 1,
                    "main": 1,
                    "useip": 1,
                    "ip": host,
                    "dns": "",
                    "port": "10050"
                }
            ],
            "groups":[
                {
                    "groupid": groupid
                }
            ],
            "templates":[
                {
                    "templateid": tempid
                }
            ]
        }
        response = self.do_request("host.create",params,authid,url)
        if 'result' in response:
            try:
                hostid = response['result']['hostids']
                return True
            except Exception as e :
                print e
                logger.error("%s zabbix add host:%s" %(host,e))
                return False
        else:
            print response['error']['data'].encode('utf-8')
            logger.error("%s add host error:%s" %(host,response['error']['data'].encode('utf-8')))
            return False
    def update_host_proxy(self,host,proxy_hostid,url):
        authid = self.auth(url)
        response = self.get(host,url)
        hostid=""
        try:
            hostid = response['result'][0]['hostid']
        except Exception as e:
            return True
        params = {
            "hostid": hostid,
            "proxy_hostid":proxy_hostid
        }
        response = self.do_request("host.update",params,authid,url)
        
        if 'result' in response:
            try:
                hostid = response['result']['hostids']
                return True
            except Exception as e :
                print e
                logger.error("%s zabbix add host:%s" %(host,e))
                return False
        else:
            print response['error']['data'].encode('utf-8')
            logger.error("%s add host error:%s" %(host,response['error']['data'].encode('utf-8')))
            return False

    def get_conf_content(self,host):
        sta,val = commands.getstatusoutput("ansible %s -m shell -a 'cat /opt/aspire/product/zabbix/conf/zabbix_agentd.conf' -u tyyw03 -s"%host)
        if sta==0:
            con = val.split("\n")
            del con[0]
            return "\n".join(con)
        else:
            return ""
    def insert_cmdb(self,host):
        try:
            conf= self.get_conf_content(host)
            selectSql = "select ID from cmdb_zabbix_infomation where ip=%s"
            count = cur.execute(selectSql,(host))
            if count >=1:
                id=cur.fetchall()[0][0]
                sql="update cmdb_zabbix_infomation set HOSTNAME=%s,PROCESS_STATUS=%s,ZABBIX_PATH=%s,AGENTDCONF=%s,CREATE_DATE=%s where id=%s"
                cur.execute(sql,(self.hostname,"True","/opt/aspire/product/zabbix/",conf,time.strftime('%Y-%m-%d'),id))
            else:
                sql="""
                insert into cmdb_zabbix_infomation(ID,IP,HOSTNAME,PROCESS_STATUS,ZABBIX_PATH,AGENTDCONF,CREATE_DATE) values
                (%s,%s,%s,%s,%s,%s,%s)
                """
                cur.execute(sql,(uuid.uuid4(),host,self.hostname,"True","/opt/aspire/product/zabbix/",conf,time.strftime('%Y-%m-%d')))
            conn.commit()
        except MySQLdb.Error, e:
            logger.error(e)
        finally:
            if conn:
                cur.close()
                conn.close()

    def auto_add(self,url, host, groupid, tempid, proxy):
        if self.isexist(host,url,self.type):
            if self.check(host,url):
                print "%s check correct"%host
        else:
            #check_conf_result = self.check_conf(host,self.type)
            check_conf_result=True
            if check_conf_result:
                if self.add(url, host, groupid, tempid, proxy) and self.check(host,url):
                    self.insert_cmdb(host)
                    print "%s auto_add success"%host
            #else:
                #print "%s auto_add failed"%host



    #获取融合通信proxy主机
    def get_rhtx_proxy(self):
        myConn={"user":"zabbixsvr","pwd":"zabbix_db_2015","host":"10.1.220.52","port":"1521","sid":"zabdb11"}
        dsn = cx_Oracle.makedsn(myConn["host"],myConn["port"],myConn["sid"])
        conn = cx_Oracle.connect(myConn["user"],myConn["pwd"],dsn)
        cur = conn.cursor()
        sql="""
        select a.hostid,a.host,p.proxy_hostid,i.ip,d.total from
        (select hostid,host from hosts where host in(select host from hosts where status=5) and status=0) a,
        (select hostid as proxy_hostid,host from hosts where status=5) p,
        (select distinct proxy_hostid,count(proxy_hostid) as total from hosts group by proxy_hostid) d,
        interface i
        where a.host=p.host and a.hostid=i.hostid and d.proxy_hostid=p.proxy_hostid and p.host != 'rcs_linux_proxy01'
        and p.host != 'rcs_device_proxy01' order by d.total asc
        """
        cur.execute(sql)
        fc = cur.fetchall()
        return fc
        cur.close()
        conn.close()
    #获取资源池proxy主机
    def get_zyc_proxy(self):
        myConn={"user":"zabbix","pwd":"zabbix","host":"*","port":"1521","sid":"*"}
        dsn = cx_Oracle.makedsn(myConn["host"],myConn["port"],myConn["sid"])
        conn = cx_Oracle.connect(myConn["user"],myConn["pwd"],dsn)
        cur = conn.cursor()
        sql="""
        select a.hostid,a.host,p.proxy_hostid,i.ip,d.total from
        (select hostid,host from hosts where host in(select host from hosts where status=5) and status=0) a,
        (select hostid as proxy_hostid,host from hosts where status=5) p,
        (select distinct proxy_hostid,count(proxy_hostid) as total from hosts group by proxy_hostid) d,
        interface i
        where a.host=p.host and a.hostid=i.hostid and d.proxy_hostid=p.proxy_hostid order by total asc
        """
        cur.execute(sql)
        fc = cur.fetchall()
        return fc
        cur.close()
        conn.close()
    #获取MM proxy主机
    def get_mm_proxy(self):
        myConn={"user":"zabbix","pwd":"zabbix","host":"*","port":"1521","sid":"*"}
        dsn = cx_Oracle.makedsn(myConn["host"],myConn["port"],myConn["sid"])
        conn = cx_Oracle.connect(myConn["user"],myConn["pwd"],dsn)
        cur = conn.cursor()
        sql="""
        select a.hostid,a.host,p.proxy_hostid,i.ip,d.total from
        (select hostid,host from hosts where host in(select host from hosts where status=5) and status=0) a,
        (select hostid as proxy_hostid,host from hosts where status=5) p,
        (select distinct proxy_hostid,count(proxy_hostid) as total from hosts group by proxy_hostid) d,
        interface i
        where a.host=p.host and a.hostid=i.hostid and d.proxy_hostid=p.proxy_hostid  order by total asc
        """
        cur.execute(sql)
        fc = cur.fetchall()
        return fc
        cur.close()
        conn.close()
    def get_connect_proxy(self,host,record):
        for re in record:
            if self.check_port(host,re[3]):
                return re
            else:
                continue

    def get_hostgroup(self,url,business):
        myConn={"user":"zabbix","pwd":"zabbix","host":"*","port":"1521","sid":"*"}
        dsn = cx_Oracle.makedsn(myConn["host"],myConn["port"],myConn["sid"])
        conn = cx_Oracle.connect(myConn["user"],myConn["pwd"],dsn)
        cur = conn.cursor()
        sql="select * from sjzd_zabbix_ums where ch = '%s'" %(business)
        cur.execute(sql)
        fc=cur.fetchall()
        if len(fc)>0:
            authid=self.auth(url)
            params = {
                "output": "extend",
                "filter": {
                "name": [
                    fc[0][0]
                ]
                }
            }
            response = self.do_request('hostgroup.get',params,authid,url)
            if 'result' in response:
                if response['result']:
                    return response['result'][0]['groupid']
                else:
                    return None
            else:
                return None
        else:
            return None

if __name__ == '__main__':
    ##log moduel initial start#
    LOG_FILE = "/opt/aspire/autoweb/script/zabbix/log/"+time.strftime('%Y%m%d%H%M',time.localtime(time.time()))+".log"
    #handler = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes = 1024*1024, backupCount = 5)
    handler = logging.FileHandler(LOG_FILE)
    handler.setLevel(logging.DEBUG)
    fmt = '%(asctime)s - %(filename)s:%(lineno)s -[%(levelname)s] - %(message)s'
    formatter = logging.Formatter(fmt)
    handler.setFormatter(formatter)
    logger = logging.getLogger('zabbix_api')
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    ##log module initial completed#

    parser = argparse.ArgumentParser(description='zabbix  api ',usage='%(prog)s [options]')
    parser.add_argument('-A','--add-host',dest='addhost',nargs=3,metavar=('server_type','host','business'),help='add host')
    parser.add_argument('-O','--auth-host',dest='autohost',nargs=3,metavar=('server_type','host','business'),help='add host')
    parser.add_argument('-D','--delete-host',dest='delhost',nargs=2,metavar=('server_type','hostid'),help='delete host')
    parser.add_argument('-C','--check-host',dest='checkhost',nargs=1,metavar=('host'),help='delete host')
    if len(sys.argv)==1:
        print parser.print_help()
    else:
        args = parser.parse_args()
        zabbix = auto_zabbix()
        if args.addhost:
            #'1'表示融合通信
            if args.addhost[0] == 'RHTX':
                zabbix.type='RHTX'
                url = zabbix_rhtx
                groupid = zabbix.get_hostgroup(url,args.addhost[2])
                if not groupid:
                    groupid='219'
                tempid='10745'
                proxy =zabbix.get_rhtx_proxy()
                proxy_hostid =zabbix.get_rhtx_proxy()[0][2]
            #'2'表示资源池
            elif args.addhost[0] == 'ZYC':
                zabbix.type='ZYC'
                url = zabbix_zyc
                groupid=zabbix.get_hostgroup(url,args.addhost[2])
                if not groupid:
                    groupid='203'
                tempid='10107'
                proxy = zabbix.get_zyc_proxy()
                proxy_hostid =zabbix.get_zyc_proxy()[0][2]
            else:
                print ("The domain belongs to 'ZYC' or 'RHTX'")
                exit(0)
            zabbix.add(url,args.addhost[1],groupid,tempid,proxy,proxy_hostid)
        elif args.delhost:
            if args.delhost[0] == 'RHTX':
                url = zabbix_rhtx
                zabbix.type='RHTX'
            elif args.delhost[0] == 'ZYC':
                url = zabbix_zyc
                zabbix.type='ZYC'
            else:
                print ("The domain belongs to 'ZYC' or 'RHTX'")
                exit(0)
            zabbix.delete_host(url,args.delhost[1])
        elif args.checkhost:
            host = args.checkhost[0]
            print host
            url=""
            if zabbix.isexist(host,zabbix_rhtx,type='RHTX'):
                url = zabbix_rhtx
                zabbix.type='RHTX'
            elif zabbix.isexist(host,zabbix_zyc,type='ZYC'):
                url = zabbix_zyc
                zabbix.type='ZYC'
            else:
                print "%s not exists" %host
                exit(0)
            re=zabbix.check(host,url)
            if re:
                print "%s configure correct "%host
            else:
                print "%s configure error!"%host
        elif args.autohost:
            if args.autohost[0] == 'RHTX':
                zabbix.type='RHTX'
                url = zabbix_rhtx
                groupid = zabbix.get_hostgroup(url,args.autohost[2])
                if not groupid:
                    groupid='219'
                tempid='10745'
                proxy =zabbix.get_rhtx_proxy()
                proxy_hostid =zabbix.get_rhtx_proxy()[0][2]
            #'2'表示资源池
            elif args.autohost[0] == 'ZYC':
                zabbix.type='ZYC'
                url = zabbix_zyc
                groupid=zabbix.get_hostgroup(url,args.autohost[2])
                if not groupid:
                    groupid='203'
                tempid='10107'
                proxy = zabbix.get_zyc_proxy()
                proxy_hostid =zabbix.get_zyc_proxy()[0][2]
            elif args.autohost[0] == 'MM':
                zabbix.type='ZYC'
                zabbix.tag='MM'
                url = zabbix_zyc
                groupid=zabbix.get_hostgroup(url,args.autohost[2])
                if not groupid:
                    groupid='203'
                tempid='10107'
                proxy=zabbix.get_mm_proxy()
                proxy_hostid =zabbix.get_mm_proxy()[0][2]
            zabbix.auto_add(url,args.autohost[1],groupid,tempid,proxy)










