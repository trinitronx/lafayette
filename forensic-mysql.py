#!/usr/bin/env python
# encoding: utf-8

import imaplib, email, json, time, subprocess, os, re, urlparse, dns.resolver, dns.reversename, operator
import sys
import hashlib
import calendar
from datetime import date, datetime, timedelta
from dateutil.parser import parse
import MySQLdb

# local config
#
dbHost="localhost"
dbUser="root"
dbName="arf"

imapHost="localhost"
impaUser="failures"
imapPassword="password"

# end of local config

def addressInNetwork(ip, net):
   import socket,struct
   ipaddr = int(''.join([ '%02x' % int(x) for x in ip.split('.') ]), 16)
   netstr, bits = net.split('/')
   netaddr = int(''.join([ '%02x' % int(x) for x in netstr.split('.') ]), 16)
   mask = (0xffffffff << (32 - int(bits))) & 0xffffffff
   return (ipaddr & mask) == (netaddr & mask)

def domainIsSubDomain(subdomain):
	isSubDomain = False
	for domain in domains:
		if subdomain==domain or subdomain.endswith("."+domain) :
			isSubDomain = True
			break
	return isSubDomain

def getIp4ToAsn(ip):
	asn = 0
	try:
		(ip1,ip2,ip3,ip4) = ip.split(".")
		query = "%s.%s.%s.%s.origin.asn.cymru.com" % (ip4,ip3,ip2,ip1)
		reportanswers = dns.resolver.query(query, 'TXT')
		res = reportanswers[0].to_text()
		asn = long(res.split("|")[0][1:])
    	except:
      		pass
	return asn

def getDomainId(db,domain):
	if domain is None:
		domain = ""
	try:
		domain = domain.lower()
		strSql = "insert into domain (domain) values('"+domain+"')"
        	db.query(strSql)
		db.commit()
	except:
		pass
	strSql = "select domainId from domain where domain='"+domain+"';"
	db.query(strSql)
	result = db.store_result()
	if result is not None:
		row = result.fetch_row(1,1)[0]
		domainId = row['domainId']
	else:
		domainId = 0
	return domainId

def getEmailLocalId(db,local):
	if local is None:
		local = ""
        try:
		local = local.lower()
                strSql = "insert into emailLocal (emailLocal) values('"+local+"')"
                db.query(strSql)
		db.commit()
        except:
                pass
        strSql = "select emailLocalId from emailLocal where emailLocal='"+local+"';"
        db.query(strSql)
        result = db.store_result()
	if result is not None:
        	row = result.fetch_row(1,1)[0]
                emailLocalId = row['emailLocalId']
        else:
                emailLocalId = 0
        return emailLocalId

def getUrl(db,emailId,arrivalDate,listurl):
	for urlitem in listurl:
		(ip,hostname,url) = urlitem
		urlAsn = getIp4ToAsn(ip)
		urlDomainId = getDomainId(db,hostname)
		strSql1=""
		found=False
		url = db.escape_string(url)
		if len(url)>999:
			url = url[:999]
		strSql = "select urlId from url where url='"+url+"';"
                db.query(strSql)
                result = db.store_result()
                if result is not None:
                        try:
                                row = result.fetch_row(1,1)[0]
                                urlId = row['urlId']
				found=True
                        except:
                                urlId = 0
		if not found:
			try:
				strSql1 = "insert into url (firstSeen,lastSeen,urlIp,urlDomainId,urlAsn,url) values('%s','%s',INET_ATON('%s'),%s,%s,'%s')" % (arrivalDate,arrivalDate,ip,urlDomainId,urlAsn,url)
				db.query(strSql1)
				db.commit()
        		except:
                		pass
        		strSql = "select urlId from url where url='"+url+"';"
			db.query(strSql)
        		result = db.store_result()
			if result is not None:
				try:
        				row = result.fetch_row(1,1)[0]
                			urlId = row['urlId']
				except:
					print strSql1
					print strSql
					urlId = 0
        		else:
                		urlId = 0
        	try:
			strSql = "update url set lastSeen='%s' where urlId=%s" % (arrivalDate,urlId)
                        db.query(strSql)
                        db.commit()
		except:
			print strSql
			pass
		try:
                        strSql = "insert into emailUrl (emailId,urlId) values(%s,%s)" % (emailId,urlId)
                        db.query(strSql)
			db.commit()
                except:
                        pass

def getFile(db,emailId,arrivalDate,md5):
	for md5Item in md5:
		hash = md5item[0]
		filename = md5item[1][:255]
		print hash,filename
		try:
                        strSql = "insert into file (firstSeen,lastSeen,hash,filename) values('%s','%s','%s','%s')" % (arrivalDate,arrivalDate,hash,filename)
                        db.query(strSql)
                        db.commit()
                except:
                        pass
                strSql = "select fileId from file where hash='"+hash+"';"
                db.query(strSql)
                result = db.store_result()
                if result is not None:
                        row = result.fetch_row(1,1)[0]
                        fileId = row['fileId']
                else:
                        fileId = 0
                try:
                        strSql = "update file set lastSeen='%s' where urlId=%s" % (arrivalDate,fileId)
                        db.query(strSql)
                        db.commit()
                except:
			print strSql
                        pass
                try:
                        strSql = "insert into emailFile (emailId,fileId) values(%s,%s)" % (emailId,fileId)
                        db.query(strSql)
                        db.commit()
                except:
                        pass	

pid = str(os.getpid())
pidfile = "forensic-mysql.pid"

if os.path.isfile(pidfile):
    old_pid = file(pidfile, 'r').read()
    if os.path.exists("/proc/%s" % old_pid):
    	print "%s already exists, exiting" % pidfile
    	sys.exit()
    else:
	print "%s is there but process not running, removing it" % pidfile
        os.unlink(pidfile)
	
file(pidfile, 'w').write(pid)

match_urls = re.compile(r"""(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'".,<>?«»“”‘’]))""", re.DOTALL)

match_emails = re.compile(r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,4}\b',re.IGNORECASE)

liyear=0
limonth=0
liday=0

lioldyear=0
lioldmonth=0
lioldday=0

lidate=time.gmtime()

today = date.today()
yesterday = today - timedelta(days=2)
sentsince = '(SENTSINCE %s NOT SEEN)' % yesterday.strftime('%d-%b-%Y')

print sentsince

topsendingip={}
topurlip={}
topurl={}

db=MySQLdb.connect(host=dbHost,user=dbUser,db=dbName)
db.autocommit(True)

imap = imaplib.IMAP4_SSL(imapHost)
imap.login(impaUser, imapPassword)
r, data = imap.select('INBOX')
r, data = imap.search(None, sentsince)
#r, data = imap.search(None,'ALL')
ids = data[0]
id_list = ids.split()
for num in id_list:
#for num in range(12000,14000):
	r, data = imap.fetch(num, '(RFC822)')
	msg = email.message_from_string(data[0][1])
	feedbackreport = ""
	orgmsg = ""
	lisubject = ""
	lifrom = ""
	liautosubmitted = ""
	rfc822Found = False
	bounce=False
	for part in msg.walk():
		if part.get_content_type() == 'message/feedback-report':
			feedbackreport = part.get_payload()
			feedbackreportitems = feedbackreport[0].items()
		elif part.get_content_type() == 'message/rfc822' and not rfc822Found:
			msg2 = part.get_payload()
			orgmsg = msg2[0].as_string()
			lisubject = msg2[0].get('Subject')
			lifrom = msg2[0].get('From')
			liautosubmitted = msg2[0].get('Auto-submitted')
			rfc822Found = True
			
	limsg = {}
	if lisubject is not None:
		u_subject = unicode(lisubject,errors='replace')
		limsg ['subject'] = u_subject.encode("ascii",'xmlcharrefreplace')
	else:
		limsg ['subject'] = ""

	if limsg ['subject'].find("Out of Office") >=0 :
		liautosubmitted="auto-replied"
	if limsg ['subject'].find("Automatic reply") >=0 :
		liautosubmitted="auto-replied"
	if limsg ['subject'].find("Delivery Failure") >=0 :
                bounce=True
	if limsg ['subject'].find("failure notice") >=0 :
		bounce=True
        if limsg ['subject'].find("DELIVERY FAILURE") >=0 :
                bounce=True


	limsg ['feedbackType'] = ""
	limsg ['sourceIP'] = ""
	limsg ['inNetwork'] = False
	limsg ['mailFrom'] = ""
	if lifrom is not None:
		u_from = unicode(lifrom,errors='replace')
		limsg ['from'] = u_from.encode("ascii",'xmlcharrefreplace')
	else:
		limsg ['from'] = ""

	limsg ['userAgent'] = ""	
	limsg ['date'] = datetime.now()
	limsg ['messageId'] = ""
	u_orgmsg = unicode(orgmsg,errors='replace')
	limsg ['msg'] = u_orgmsg.encode("ascii",'xmlcharrefreplace')

	isInNetwork = False	
	for item in feedbackreportitems:
		if item[0] == 'Source-IP':
			ip = str(item[1])
			limsg ['sourceIP'] = unicode(ip,errors='replace')
			for network in networks:
				if addressInNetwork(ip,network):
#					print 'found!'
					isInNetwork = True
					break;
		if item[0] == 'Arrival-Date':
			try:
				lidate = parse(unicode(item[1],errors='replace').encode("ascii",'replace'))
				listrdate = str(calendar.timegm(lidate.utctimetuple()))
			except:
				listrdate = str(calendar.timegm(lidate.utctimetuple()))
			limsg['date'] = listrdate
		if item[0] == 'Original-Mail-From':
			limsg ['mailFrom'] = unicode(item[1],errors='replace')
		if item[0] == 'User-Agent':
			limsg ['userAgent'] = unicode(item[1],errors='replace')
		if item[0] == 'Feedback-Type':
			limsg ['feedbackType'] = unicode(item[1],errors='replace')
		if item[0] == 'Original-Rcpt-To':
                        limsg ['Original-Rcpt-To'] = unicode(item[1],errors='replace')
                if item[0] == 'Reported-Domain':
                        limsg ['Reported-Domain'] = unicode(item[1],errors='replace')
		if item[0] == 'Delivery-Result':
                        limsg ['Delivery-Result'] = unicode(item[1],errors='replace')
		if item[0] == 'Message-ID':
                        limsg ['messageId'] = unicode(item[1],errors='replace')
		if item[0] == 'Authentication-Results':
                        limsg ['Authentication-Results'] = unicode(item[1],errors='replace')

	limsg ['inNetwork'] = isInNetwork
	
	if limsg ['mailFrom']=="":
		bounce=True
	
	try:
		print num
		print 'message: %s %s %s mailfrom:%s from:%s rcptto:%s [%s]' % (limsg ['Reported-Domain'],time.strftime('%Y-%m-%d %H:%M:%S',time.gmtime(int(limsg['date']))),limsg ['sourceIP'],limsg ['mailFrom'],limsg ['from'],limsg ['Original-Rcpt-To'],limsg ['subject'])
	except:
		print 'message: error, %s' % num
	#print orgmsg
        #print "-------******************"
	urls=[]
	md5=[]
	msg3 = email.message_from_string(orgmsg)
	for orgpart in msg3.walk():
		ctype = orgpart.get_content_type()
		if orgpart.get_content_maintype() == 'text':
			orgmsgpart = orgpart.get_payload(decode=True)
			urls = urls + match_urls.findall(orgmsgpart)
		else:
			if ctype == 'message/delivery-status':
				bounce = True
			if orgpart.get_content_maintype() == 'application':
				orgmsgpart = orgpart.get_payload(decode=True)
				filename = orgpart.get_filename()
				if filename is None:
					filename = ""
				hash = hashlib.md5(orgmsgpart)
				md5item = [hash.hexdigest(),filename]
				md5 = md5 + [md5item]
				
	listurl=[]
	for url in urls:
		o = urlparse.urlparse(url[0])
		try:
      			reportanswers = dns.resolver.query(o.hostname, 'A')
			ip = reportanswers[0].to_text()
    		#except dns.exception.DNSException as e:
		except Exception, err:
      			ip = ""
		      	print '  A error: %s' % str(err)
		listurl = listurl +[(ip,o.hostname,url[0])]

	#storing results in db
	reportedDomainId = getDomainId(db,limsg ['Reported-Domain'])
	
	try:
		(local,domain)=limsg ['mailFrom'].split('@',2)
	except:
		local = ""
		domain = ""
	originalMailFromLocalId = getEmailLocalId(db,local)
	originalMailFromDomainId = getDomainId(db,domain)
	
	try:
		(local,domain)=limsg ['Original-Rcpt-To'].split('@',2)
        except:
                local = ""
                domain = ""
        originalRcptToLocalId = getEmailLocalId(db,local)
        originalRcptToDomainId = getDomainId(db,domain)

	reverse = dns.reversename.from_address(limsg ['sourceIP'])
	try:
		reportanswers = dns.resolver.query(reverse, 'PTR')
                domain = reportanswers[0].to_text()
	#except dns.exception.DNSException as e:
	except Exception, err:
		domain = ""
		print '  PTR error: %s' % str(err)
	sourceDomainId = getDomainId(db,domain)

	res = match_emails.findall(limsg ['from'])
	try:
                (local,domain)=res[0].split('@',2)
        except:
                local = ""
                domain = ""
        originalFromLocalId = getEmailLocalId(db,local)
        originalFromDomainId = getDomainId(db,domain)

	sourceAsn = getIp4ToAsn(limsg ['sourceIP'])

	deliveryResult="none"
	if "dis=reject" in limsg ['Authentication-Results']:
		deliveryResult="reject"
	if "dis=quarantine" in limsg ['Authentication-Results']:
		deliveryResult="quarantine"

	try:
		arrivalDate = time.strftime('%Y-%m-%d %H:%M:%S',time.gmtime(int(limsg['date'])))
		strSql = "INSERT INTO arfEmail("
		strSql = strSql + "feedbackType,"
		strSql = strSql + "emailType,"
		strSql = strSql + "originalMailFromLocalId, originalMailFromDomainId,originalRcptToLocalId,originalRcptToDomainId,"
		strSql = strSql + "arrivalDate,messageId,authenticationResults,sourceIp, sourceDomainId, sourceAsn,"
                strSql = strSql + "deliveryResult,"
		strSql = strSql + "reportedDomainId,"
		strSql = strSql + "originalFromLocalId, originalFromDomainId,"
		strSql = strSql + "subject,content)"
		strSql = strSql + " VALUES("
		strSql = strSql + "'%s'," % limsg ['feedbackType']
		if bounce:
			strSql = strSql + "'bounce',"
		elif liautosubmitted == "auto-replied":
			strSql = strSql + "'auto-replied'," 
		else:
			strSql = strSql + "'normal',"
		strSql = strSql + "%s,%s," % (originalMailFromLocalId,originalMailFromDomainId)
       		strSql = strSql + "%s,%s," % (originalRcptToLocalId,originalRcptToLocalId)
		strSql = strSql + "'%s','%s','%s',INET_ATON('%s'),%s," % (arrivalDate,limsg ['messageId'],limsg ['Authentication-Results'],limsg ['sourceIP'],sourceDomainId)
        	strSql = strSql + "%s," % (sourceAsn)
                strSql = strSql + "'%s'," % (deliveryResult)
		strSql = strSql + "%s," % (reportedDomainId)
        	strSql = strSql + "%s,%s," % (originalFromLocalId, originalFromDomainId)
		strSql = strSql + "'%s','%s'" % (db.escape_string(limsg ['subject']),db.escape_string(limsg['msg']))
        	#strSql = strSql + "%s','%s'" % (limsg ['subject'],limsg['msg'])
		strSql = strSql + ")"
		#print strSql
		cur = db.cursor()
		cur.execute(strSql)
		emailId = cur.lastrowid
		db.commit()
		cur.close()
		print emailId
		getUrl(db,emailId,arrivalDate,listurl)
		print "1 ",
		getFile(db,emailId,arrivalDate,md5)
		print "2 ",
		imap.store(num,'+FLAGS', '\\Seen')
		imap.store(num,'+FLAGS', '\\Deleted')
		print "3"
	except:
		print "error, cannot store info in db\n"
	print "-------******************"
print "Expunging now"
imap.expunge()
imap.logout()

os.unlink(pidfile)