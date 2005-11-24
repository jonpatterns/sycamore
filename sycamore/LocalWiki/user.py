# -*- coding: iso-8859-1 -*-
"""
    LocalWiki - User Accounts

    @copyright: 2000-2004 by J?rgen Hermann <jh@web.de>
    @license: GNU GPL, see COPYING for details.
"""

# Imports
import os, string, time, Cookie, sha, locale, pickle
from LocalWiki import config, wikiutil, wikidb
from LocalWiki.util import datetime
import xml.dom.minidom

#import sys

#############################################################################
### Helpers
#############################################################################


def getUserList():
    """
    Get a list of all (numerical) user IDs.
    
    @rtype: list
    @return: all user IDs
    """
    all_ids = []
    db = wikidb.connect()
    cursor = db.cursor()
    cursor.execute("SELECT id from users")
    userid = cursor.fetchone()
    while userid:
      all_ids.append(userid[0])
      userid = cursor.fetchone()
    cursor.close()
    db.close()
    return all_ids


_name2id = None

def getUserId(searchName):
    """
    Get the user ID for a specific user NAME.

    @param searchName: the user name to look up
    @rtype: string
    @return: the corresponding user ID or None
    """
    db = wikidb.connect()
    cursor = db.cursor()
    cursor.execute("SELECT id from users where name=%s", (searchName))
    result = cursor.fetchone()
    cursor.close()
    db.close()
    if result:  id = result[0]
    else: id = ''

    return id

def getUserIdentification(request, username=None):
    """ 
    Return user name or IP or '<unknown>' indicator.
    
    @param request: the request object
    @param username: (optional) user name
    @rtype: string
    @return: user name or IP or unknown indicator
    """
    _ = request.getText

    if username is None:
        username = request.user.name

    return username or request.remote_addr or _("<unknown>")


def encodePassword(pwd):
    """
    Encode a cleartext password, compatible to Apache htpasswd SHA encoding.

    @param pwd: the cleartext password
    @rtype: string
    @return: the password in apache htpasswd compatible SHA-encoding
    """
    return hash(pwd)

def hash(cleartext):
    """
    SHA hash of cleartext returned
    """
    import base64
    return base64.encodestring(sha.new(cleartext).digest()).rstrip()


#############################################################################
### User
#############################################################################

class User:
    """A LocalWiki User"""

    _checkbox_fields = [
         ('edit_on_doubleclick', lambda _: _('Open editor on double click')),
         ('remember_me', lambda _: _('Remember login information forever (so you don\'t have to keep logging in)')),
         ('disabled', lambda _: _('Disable this account forever')),
    ]
    _transient_fields =  ['id', 'valid', 'may', 'auth_username', 'trusted']
    _MAX_TRAIL = config.trail_size

    def __init__(self, request, id=None, name="", password=None, auth_username=""):
        """
        Initialize user object
        
        @param request: the request object
        @param id: (optional) user ID
        @param name: (optional) user name
        @param password: (optional) user password
        @param auth_username: (optional) already authenticated user name (e.g. apache basic auth)
        """
        self.valid = 0
        self.id = id
        if auth_username:
            self.auth_username = auth_username
        elif request:
            self.auth_username = request.auth_username
        else:
            self.auth_username = ""
        self.name = name
        if not password:
            self.enc_password = ""
        else:
            self.enc_password = encodePassword(password)
        self.trusted = 0
        self.email = ""
        self.edit_rows = config.edit_rows
        self.edit_cols = 80
        self.last_saved = str(time.time())
        self.css_url = ""
        self.language = ""
        self.favorited_pages = ""
        self.theme_name = config.theme_default
        # if an account is disabled, it may be used for looking up
        # id -> username for page info and recent changes, but it
        # is not usabled for the user any more:
        # self.disabled   = 0
        # is handled by checkbox now.
        
        # attrs not saved to profile
        self._request = request
        self._trail = []

        # create checkbox fields (with default 0)
        for key, label in self._checkbox_fields:
            setattr(self, key, 0)

        self.remember_me = 1

        if not self.auth_username and not self.id:
            try:
                cookie = Cookie.SimpleCookie(request.saved_cookie)
            except Cookie.CookieError:
                # ignore invalid cookies, else user can't relogin
                cookie = None
            if cookie and cookie.has_key(wikiutil.quoteFilename(config.sitename)+'ID'):
		# does their cookie pass our super elite test?
		if self.isValidCookieDough(cookie[wikiutil.quoteFilename(config.sitename)+'ID'].value):
			# okay, lets let them in
       	        	self.id = self.getUserIdDough(cookie[wikiutil.quoteFilename(config.sitename)+'ID'].value)
			

        # we got an already authenticated username:
        if not self.id and self.auth_username:
            self.id = getUserId(self.auth_username)

        if self.id:
            self.load_from_id()
            if self.name == self.auth_username:
                self.trusted = 1
        elif self.name:
            self.load()
        else:
            #!!! this should probably be a hash of REMOTE_ADDR, HTTP_USER_AGENT
            # and some other things identifying remote users, then we could also
            # use it reliably in edit locking
            from random import randint
            self.id = "%s.%d" % (str(time.time()), randint(0,65535))
            
        # "may" so we can say "if user.may.edit(pagename):"
        if config.SecurityPolicy:
            self.may = config.SecurityPolicy(self)
        else:
            from security import Default
            self.may = Default(self)


#    def __filename(self):
#        """
#        get filename of the user's file on disk
#        @rtype: string
#        @return: full path and filename of user account file
#        """
#        return os.path.join(config.user_dir, self.id or "...NONE...")


    def exists(self):
        """
        Do we have a user account for this user?
        
        @rtype: bool
        @return: true, if we have a user account
        """
	db = wikidb.connect()
	cursor = db.cursor()
	cursor.execute("SELECT id from users where id=%s", (self.id))
	result = cursor.fetchone()
	cursor.close()
	db.close()
	if result: return True
	else:  return False
        return False

    def load(self):
        """
        Lookup user ID by user name and load user account.

        Can load user data if the user name is known, but only if the password is set correctly.
        """
        self.id = getUserId(self.name)
        if self.id:
            self.load_from_id(1)
        #print >>sys.stderr, "self.id: %s, self.name: %s" % (self.id, self.name)
        
    def load_from_id(self, check_pass=0):
        """
        Load user account data from disk.

        Can only load user data if the id number is already known.

        This loads all member variables, except "id" and "valid" and
        those starting with an underscore.
        
        @param check_pass: If 1, then self.enc_password must match the
                           password in the user account file.
        """
        if not self.exists(): return

        # XXX UNICODE fix needed, we want to read utf-8 and decode to unicode
	db = wikidb.connect()
	cursor = db.cursor()
	cursor.execute("SELECT name, email, enc_password, language, remember_me, css_url, disabled, edit_cols, edit_rows, edit_on_doubleclick, theme_name, UNIX_TIMESTAMP(last_saved) from users where id=%s", (self.id))
	data = cursor.fetchone()
	cursor.close()
	db.close()

        user_data = {'enc_password': ''}
        user_data['name'] = data[0] 
	user_data['email'] = data[1]
	user_data['enc_password'] = data[2]
	user_data['language'] = data[3]
	user_data['remember_me'] = data[4]
	user_data['css_url'] = data[5]
	user_data['disabled'] = data[6]
	user_data['edit_cols'] = data[7]
	user_data['edit_rows'] = data[8]
	user_data['edit_on_doubleclick'] = data[9]

	user_data['theme_name'] = data[10]
	user_data['last_saved'] = data[11]

        if check_pass:
            # If we have no password set, we don't accept login with username
            if not user_data['enc_password']:
                return
            # Check for a valid password
            elif user_data['enc_password'] != self.enc_password:
                # print >>sys.stderr, "File:%s Form:%s" % (user_data['enc_password'], self.enc_password)
                return
            else:
                self.trusted = 1

        # Copy user data into user object
        for key, val in user_data.items():
            vars(self)[key] = val


        # old passwords are untrusted
        if hasattr(self, 'password'): del self.password
        if hasattr(self, 'passwd'): del self.passwd

        # make sure checkboxes are boolean
        for key, label in self._checkbox_fields:
            try:
                setattr(self, key, int(getattr(self, key)))
            except ValueError:
                setattr(self, key, 0)

        # convert (old) hourly format to seconds
        #if -24 <= self.tz_offset and self.tz_offset <= 24:
        #    self.tz_offset = self.tz_offset * 3600

        # clear trail
        self._trail = []

        if not self.disabled:
            self.valid = 1


    def save(self):
        """
        Save user account data to user account file on disk.

        This saves all member variables, except "id" and "valid" and
        those starting with an underscore.
        """
        if not self.id: return

        self.last_saved = str(time.time())

	db = wikidb.connect()
	cursor = db.cursor()
	cursor.execute("start transaction;")
	if self.exists():	
		cursor.execute("update users set id=%s, name=%s, email=%s, enc_password=%s, language=%s, remember_me=%s, css_url=%s, disabled=%s, edit_cols=%s, edit_rows=%s, edit_on_doubleclick=%s, theme_name=%s, last_saved=FROMT_UNIXTIME(%s) where id=%s", (self.id, self.name, self.email, self.enc_password, self.language, str(self.remember_me), self.css_url, str(self.disabled), self.edit_cols, self.edit_rows, str(self.edit_on_doubleclick), self.theme_name, self.last_saved, self.id))
	else:
		cursor.execute("insert into users set id=%s, name=%s, email=%s, enc_password=%s, language=%s, remember_me=%s, css_url=%s, disabled=%s, edit_cols=%s, edit_rows=%s, edit_on_doubleclick=%s, theme_name=%s, last_saved=FROM_UNIXTIME(%s), join_date=FROM_UNIXTIME(%s)", (self.id, self.name, self.email, self.enc_password, self.language, str(self.remember_me), self.css_url, str(self.disabled), self.edit_cols, self.edit_rows, str(self.edit_on_doubleclick), self.theme_name, self.last_saved, time.time()))
	cursor.execute("commit;")
	cursor.close()
	db.close()


    def makeCookieHeader(self):
        """
        Make the Set-Cookie header for this user
            
        uses: config.cookie_lifetime (int) [hours]
            == 0  --> cookie will live forever (no matter what user has configured!)
            > 0   --> cookie will live for n hours (or forever when "remember_me")
            < 0   --> cookie will live for -n hours (forced, ignore "remember_me"!)
        """
        lifetime = int(config.cookie_lifetime) * 3600
        forever = 10*365*24*3600 # 10 years, after this time the polar icecaps will have melted anyway
        now = time.time()
        if not lifetime:
            expire = now + forever
        elif lifetime > 0:
            if self.remember_me:
                expire = now + forever
            else:
                expire = now + lifetime
        elif lifetime < 0:
            expire = now + (-lifetime)

        # XXX maybe better make this a critical section for persistent environments!?
        loc=locale.setlocale(locale.LC_TIME, 'C')
        expirestr = time.strftime("%A, %d-%b-%Y %H:%M:%S GMT", time.gmtime(expire))
        locale.setlocale(locale.LC_TIME, loc)

        cookie = Cookie.SimpleCookie()
	sessionid, secret = self.cookieDough(expire)
        cookie[wikiutil.quoteFilename(config.sitename)+'ID'] = self.id + ',' + sessionid + ',' + secret
	cookie_dir = config.web_dir
	if not cookie_dir: cookie_dir = '/'
        return "%s expires=%s;host=%s;Path=%s" % (cookie.output(), expirestr, config.domain, cookie_dir)


    def cookieDough(self, expiretime):
	"""
	Creates a session-specific secret that is stored in the user's cookie.
	Stores a hashed version of of this secret in a session dictionary.
	@return pair:  session id associated with the secret, string containing the secret
	----
	the session dict is key'd by the session id
	  and each node of the list is a (hashed secret, time of creation) pair
	"""
	import random, cPickle
	secret = hash(str(random.random()))
	
	sessionid = hash(str(time.time()) + str(self.id))
	db = wikidb.connect()
	cursor = db.cursor()
	cursor.execute("start transaction;")
	# clear possibly old expired sessions
	cursor.execute("DELETE from userSessions where user_id=%s and expire_time>=FROM_UNIXTIME(%s)", (self.id, time.time()))
	# add our new session
	cursor.execute("INSERT into userSessions set user_id=%s, session_id=%s, secret=%s, expire_time=FROM_UNIXTIME(%s)", (self.id, sessionid, hash(secret), expiretime))
	cursor.execute("commit")
	cursor.close()
	db.close()

	return (sessionid, secret)
    
    def getUserIdDough(self, cookiestring):
	"""
	return the user id from the cookie
	"""
	return (cookiestring.split(','))[0]

    def isValidCookieDough(self, cookiestring):
	split_string = cookiestring.split(',')
	userid = split_string[0]
	sessionid = split_string[1]
	secret = split_string[2]
	db = wikidb.connect()
	cursor = db.cursor()
	cursor.execute("SELECT secret from userSessions where user_id=%s and session_id=%s and expire_time>=FROM_UNIXTIME(%s)", (userid, sessionid, time.time()))
	result = cursor.fetchone()
	cursor.close()
	db.close()
	if result:
	  if hash(secret) == result[0]: return True
	else: return False

	
    def sendCookie(self, request):
        """
        Send the Set-Cookie header for this user.
        
        @param request: the request object
        """
        # prepare to send cookie
	cookie_header = self.makeCookieHeader()
        request.setHttpHeader(cookie_header)

        # create a "fake" cookie variable so the rest of the
        # code works as expected
        try:
            cookie = Cookie.SimpleCookie(request.saved_cookie)
        except Cookie.CookieError:
            # ignore invalid cookies, else user can't relogin
            request.saved_cookie = cookie_header
        else:
            if not cookie.has_key(wikiutil.quoteFilename(config.sitename)+'ID'):
                request.saved_cookie = cookie_header


    def getTime(self, tm):
        """
        Get time in user's timezone.
        
        @param tm: time (UTC UNIX timestamp)
        @rtype: int
        @return: tm tuple adjusted for user's timezone
        """
        return datetime.tmtuple(tm + config.tz_offset_unix)


    def getFormattedDate(self, tm):
        """
        Get formatted date adjusted for user's timezone.

        @param tm: time (UTC UNIX timestamp)
        @rtype: string
        @return: formatted date, see config.date_fmt
        """
        return time.strftime(config.date_fmt, self.getTime(tm))

    def getFormattedDateWords(self, tm):
        return time.strftime("%A, %B %d, %Y", self.getTime(tm))

    def getFormattedDateTime(self, tm):
        """
        Get formatted date and time adjusted for user's timezone.

        @param tm: time (UTC UNIX timestamp)
        @rtype: string
        @return: formatted date and time, see config.datetime_fmt
        """
        datetime_fmt = config.datetime_fmt
        return time.strftime(datetime_fmt, self.getTime(tm))


    def setShowComments(self, hideshow):
        """
        Set whether or not we show the comments on the RC page.

        @param tm: time (UTC UNIX timestamp), default: current time
        """
        if self.valid:
	    bool_show= '1'
	    if hideshow == 'showcomments' : bool_show= '1'
	    elif hideshow == 'hidecomments' : bool_show= '0'
	    db = wikidb.connect()
	    cursor = db.cursor()
	    cursor.execute("start transaction;")
	    cursor.execute("update users set rc_showcomments=%s where id=%s", (bool_show, self.id))
	    cursor.execute("commit;")
	    cursor.close()
	    db.close()

    def getShowComments(self):
        """
        Get whether or not we show comments on the RC page.

        @rtype: int
        @return: bookmark time (UTC UNIX timestamp) or None
        """
        if self.valid and self.exists():
 	    db = wikidb.connect()
	    cursor = db.cursor()
	    cursor.execute("SELECT rc_showcomments from users where id=%s", (self.id))
	    result = cursor.fetchone()
	    cursor.close()
	    db.close()
	    # just in case..
	    if not result:  return 1
	    if result[0] == 1: return 1
	    else:  return 0
		
        return 1

    def setBookmark(self, tm = None):
        """
        Set bookmark timestamp.
        
        @param tm: time (UTC UNIX timestamp), default: current time
        """
        if self.valid:
            if not tm: tm = time.time()
	    db = wikidb.connect()
	    cursor = db.cursor()
	    cursor.execute("start transaction;")
	    cursor.execute("UPDATE users set rc_bookmark=FROM_UNIXTIME(%s) where id=%s", (str(tm), self.id))
	    cursor.execute("commit;")
	    cursor.close()
	    db.close()

    def setFavBookmark(self, pagename, tm = None):
        """
        Set Favorites bookmark timestamp.

        @param tm: time (UTC UNIX timestamp), default: current time
        """
        if self.valid:
            if not tm: tm = time.time()
            import re
            #bmfile = open(self.__filename() + ".favbookmark", "w")
            #bmfile.write(str(tm)+"\n")
            #bmfile.close()
            #try:
            #    os.chmod(self.__filename() + ".favbookmark", 0666 & config.umask)
            #except OSError:
            #    pass
            #try:
            #    os.utime(self.__filename() + ".favbookmark", (tm, tm))
            #except OSError:
            #    pass
            from LocalWiki import wikiutil
            self.favorited_pages = re.sub(r'(?i)%s\*[0-9]+\.[0-9]*\|' % wikiutil.quoteWikiname(pagename),r'%s*%s|' % (wikiutil.quoteWikiname(pagename),str(tm)),self.favorited_pages)
            self.save()


    def getBookmark(self):
        """
        Get recent changes bookmark timestamp.
        
        @rtype: int
        @return: bookmark time (UTC UNIX timestamp) or None
        """
        if self.valid:
	    db = wikidb.connect()
	    cursor = db.cursor()
	    cursor.execute("SELECT UNIX_TIMESTAMP(rc_bookmark) from users where id=%s", (self.id))
	    result = cursor.fetchone()
	    cursor.close()
	    db.close()
	    if not result: return None
	    if not result[0]: return None
	    return float(result[0])
	
        return None


    def getFavBookmark(self, pagename):
        """
        Get favorites bookmark timestamp.

        @rtype: int
        @return: bookmark time (UTC UNIX timestamp) or None
        """
        #if self.valid and os.path.exists(self.__filename() + ".favbookmark"):
        #    try:
        #        return int(open(self.__filename() + ".favbookmark", 'r').readline())
        #    except (OSError, ValueError):
        #        return None
        #return None
        #index = string.find(self.favorited_pages, pagename + "*")
        #return int(self.favorited_pages[index + len(pagename + "*"):index + 10 + len(pagename + "*")])
        #import re
        #from LocalWiki import wikiutil
	db = wikidb.connect()
        cursor = db.cursor()
        cursor.execute("SELECT UNIX_TIMESTAMP(viewTime) from userFavorites where username=%s and page=%s", (self.name, pagename))
        result = cursor.fetchone()
        cursor.close()
        db.close()
	if result: return result[0]
	else: return None


    def delBookmark(self):
        """
        Removes recent changes bookmark timestamp.

        @rtype: int
        @return: 0 on success, 1 on failure
        """
        if self.valid:
	   db = wikidb.connect()
	   cursor = db.cursor()
	   cursor.execute("start transaction;")
	   cursor.execute("update users set rc_bookmark=NULL where id=%s", (self.id))
	   cursor.execute("commit;")
	   cursor.close()
	   db.close()
	   return 0
	    
        return 1

    #def delFavBookmark(self):
    #    """
    #    Removes favorites bookmark timestamp.
#
#        @rtype: int
#        @return: 0 on success, 1 on failure
#        """
#        if self.valid:
#            if os.path.exists(self.__filename() + ".favbookmark"):
#                try:
#                    os.unlink(self.__filename() + ".favbookmark")
#                except OSError:
#                    return 1
#            return 0
#        return 1

#    def getQuickLinks(self):
#        """
#        Get list of pages this user wants in the page header.
#
#        @rtype: list
#        @return: quicklinks from user account
#        """
#        if not self.quicklinks: return []
#
#        from LocalWiki import wikiutil
#        quicklinks = self.quicklinks.split(',')
#        quicklinks = map(string.strip, quicklinks)
#        quicklinks = filter(None, quicklinks)
#        quicklinks = map(wikiutil.unquoteWikiname, quicklinks)
#        return quicklinks


#    def getSubscriptionList(self):
#        """
#        Get list of pages this user has subscribed to.
#        
#        @rtype: list
#        @return: pages this user has subscribed to
#        """
#        subscrPages = self.subscribed_pages.split(",")
#        subscrPages = map(string.strip, subscrPages)
#        subscrPages = filter(None, subscrPages)
#        return subscrPages

    def getFavoriteList(self):
        """
        Get list of pages this user has marked as a favorite.

        @rtype: list
        @return: pages this user has marked as favorites.
        """
	favPages = []
	db = wikidb.connect()
	cursor = db.cursor()
	cursor.execute("SELECT page from userFavorites where username=%s", (self.name))
	page = cursor.fetchone()
	while page:
	   favPages.append(page[0])
	   page=cursor.fetchone()
	cursor.close()
	db.close()
	return favPages

    def checkFavorites(self, pagename):
        """
        Checks to see if pagename is in the favorites list, and if it is, it updates the timestamp.
        """
        if self.name:
	  db = wikidb.connect()
	  cursor = db.cursor()
	  cursor.execute("SELECT page from userFavorites where username=%s and page=%s", (self.name, pagename))
	  result = cursor.fetchone()
	  if result:
          # we have it as a favorite
	     cursor.execute("start transaction")
	     cursor.execute("UPDATE userFavorites set viewTime=FROM_UNIXTIME(%s) where username=%s and page=%s", (time.time(), self.name, pagename)) 
	     cursor.execute("commit")
 	  
	  cursor.close()
	  db.close()

    def isFavoritedTo(self, pagename):
        """
        Check if the page is a user's favorite       
 
        @param page: page to check for subscription
        @rtype: int
        @return: 1, if user has page in favorited pages ("Bookmarks")
                 0, if not
        """
        if self.valid:
	    db = wikidb.connect()
	    cursor = db.cursor()
	    cursor.execute("SELECT page from userFavorites where username=%s and page=%s", (self.name, pagename))
	    result = cursor.fetchone()
	    cursor.close()
	    db.close()
	    if result: return 1
	    else: return 0

#    def isSubscribedTo(self, pagelist):
#        """
#        Check if user subscription matches any page in pagelist.
#        
#        @param pagelist: list of pages to check for subscription
#        @rtype: int
#        @return: 1, if user has subscribed any page in pagelist
#                 0, if not
#        """
#        import re
#
#        matched = 0
#        if self.valid:
#            pagelist_lines = '\n'.join(pagelist)
#            for pattern in self.getSubscriptionList():
#                # check if pattern matches one of the pages in pagelist
#                matched = pattern in pagelist
#                if matched: break
#                try:
#                    rexp = re.compile("^"+pattern+"$", re.M)
#                except re.error:
#                    # skip bad regex
#                    continue
#                matched = rexp.search(pagelist_lines)
#                if matched: break
#        if matched:
#            return 1
#        else:
#            return 0
#
#
#    def subscribePage(self, pagename):
#        """
#        Subscribe to a wiki page.
#
#        Note that you need to save the user data to make this stick!
#
#        @param pagename: name of the page to subscribe
#        @rtype: bool
#        @return: true, if page was NEWLY subscribed.
#        """
#        subscrPages = self.getSubscriptionList()
#
#        # add page to subscribed pages property
#        if pagename not in subscrPages: 
#            subscrPages.append(pagename)
#            self.subscribed_pages = ','.join(subscrPages)
#            return 1
#
#        return 0

    def favoritePage(self, pagename):
        """
        Favorite a wiki page.
        
        @param pagename: name of the page to subscribe
        @rtype: bool
        @return: true, if page was NEWLY subscribed.
        """ 
	if not self.isFavoritedTo(pagename):
	    db = wikidb.connect()
	    cursor = db.cursor()
	    cursor.execute("start transaction")
	    cursor.execute("INSERT into userFavorites set page=%s, username=%s, viewTime=FROM_UNIXTIME(%s)", (pagename, self.name, time.time()))
	    cursor.execute("commit")
	    cursor.close()
	    db.close()
	    return 1

        return 0


    def delFavorite(self, pagename):
	if self.isFavoritedTo(pagename):	
	   db = wikidb.connect()
	   cursor = db.cursor()
	   cursor.execute("start transaction")
	   cursor.execute("DELETE from userFavorites where page=%s and username=%s", (pagename, self.name))
	   cursor.execute("commit")
	   cursor.close()
	   db.close()
           return 1

        return 0


    def addTrail(self, pagename):
        """
        Add page to trail.
        
        @param pagename: the page name to add to the trail
        """
        if self.valid:
            # load trail if not known
            self.getTrail()      
            
            # don't append tail to trail ;)
            if self._trail and self._trail[-1] == pagename: return

            # append new page, limiting the length
            self._trail = filter(lambda p, pn=pagename: p != pn, self._trail)
            self._trail = self._trail[-(self._MAX_TRAIL-1):]
            self._trail.append(pagename)

            # save new trail
            # XXX UNICODE fix needed, encode as utf-8
            trailfile = open(self.__filename() + ".trail", "w")
            trailfile.write('\n'.join(self._trail))
            trailfile.close()
            try:
                os.chmod(self.__filename() + ".trail", 0666 & config.umask)
            except OSError:
                pass


    def getTrail(self):
        """
        Return list of recently visited pages.
        
        @rtype: list
        @return: pages in trail
        """
        if self.valid \
                and not self._trail \
                and os.path.exists(self.__filename() + ".trail"):
            try:
                # XXX UNICODE fix needed, decode from utf-8
                self._trail = open(self.__filename() + ".trail", 'r').readlines()
            except (OSError, ValueError):
                self._trail = []
            else:
                self._trail = filter(None, map(string.strip, self._trail))
                self._trail = self._trail[-self._MAX_TRAIL:]
        return self._trail
