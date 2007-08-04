# -*- coding: utf-8 -*-
"""
    Sycamore - comments macro.

    @copyright: 2005-2007 by Philip Neustrom <philipn@gmail.com>
    @license: GNU GPL, see COPYING for details.
"""

# Imports
import time
import string
import thread
import os

from Sycamore import config
from Sycamore import user
from Sycamore import util
from Sycamore import wikiutil
from Sycamore import request

from Sycamore.Page import Page
from Sycamore.PageEditor import PageEditor
from Sycamore.request import RequestBase
from Sycamore.user import User

def execute(pagename, request):
    _ = request.getText
    actname = __name__.split('.')[-1]
    page = PageEditor(pagename, request)
    msg = ''
    oldtext = page.get_raw_body()
    everything_is_okay = 0

    # be extra paranoid
    if (actname in config.excluded_actions or not
        request.user.may.edit(page)):
            msg = _('You are not allowed to edit this page. '
                    '(An account is needed in most cases)')
    
    # check whether page exists at all
    elif not page.exists():
        msg = _('This page does not exist.')

    # check whether the user clicked the delete button
    elif request.form.has_key('button') and \
        request.form.has_key('comment_text'):
        # check whether this is a valid renaming request (make outside
        # attacks harder by requiring two full HTTP transactions)
        comment_text = request.form.get('comment_text')[0]
        if request.user.anonymous:
            userId = request.user.ip
        else:
            if config.user_page_prefix:
                userId = '["%s%s"]' % (config.user_page_prefix,
                                       request.user.propercased_name)
            else:
                userId = '["%s"]' % request.user.propercased_name

        now = time.time()
        now_formatted = request.user.getFormattedDateTime(
            now, global_time=True)
        formatted_comment_text = comment_text + " --" + userId
        newtext = (oldtext + "------" + "\n" + "''" +
                   ''.join(now_formatted) + "'' [[nbsp]] " +
                   formatted_comment_text)
        page.saveText(newtext, '0',
                      comment="Comment added.", action="COMMENT_MACRO")
        msg = _('Your comment has been added.')
        
    return page.send_page(msg)
