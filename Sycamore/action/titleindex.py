# -*- coding: iso-8859-1 -*-
"""
    Sycamore - "titleindex" action

    This action generates a plain list of pages, so that other wikis
    can implement http://www.usemod.com/cgi-bin/mb.pl?MetaWiki more
    easily.

    @copyright: 2001 by J�rgen Hermann <jh@web.de>
    @license: GNU GPL, see COPYING for details.
"""

from Sycamore import config, util, wikiutil
from Sycamore.Page import Page


def execute(pagename, request):
    form = request.form

    # get the MIME type
    if form.has_key('mimetype'):
        mimetype = form['mimetype'][0]
    else:
        mimetype = "text/plain"

    request.http_headers(["Content-Type: " + mimetype])

    pages = wikiutil.getPageList(request, alphabetize=true)

    pages = [Page(pagename, request) for pagename in pages]
    pages = filter(request.user.may.read, pages)

    if mimetype == "text/xml":
        request.write('<?xml version="1.0" encoding="%s"?>' % (config.charset,))
        request.write('<TitleIndex>')
        for name in pages:
            request.write('  <Title>%s</Title>' % (util.TranslateCDATA(name),))
        request.write('</TitleIndex>')
    else:
        for name in pages:
            request.write(name+'\n')

    raise util.SycamoreNoFooter
