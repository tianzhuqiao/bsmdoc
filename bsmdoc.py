#!python
#!/usr/bin/env python
# Copyright (C) Tianzhu Qiao (tianzhu.qiao@feiyilin.com).

import sys, re, os, io, time
import traceback
try:
    from configparser import SafeConfigParser
    from io import StringIO
except ImportError:
    from ConfigParser import SafeConfigParser  # ver. < 3.0
    from StringIO import StringIO

import ply.lex as lex
import ply.yacc as yacc

class bsmdoc_config(object):
    """
    class to hold all the global configurations
    """
    def __init__(self):
        self.html = ""
        self.config = SafeConfigParser()
        self.scan = 1
        self.rescan = False
        self.contents = None

    def get_cfg(self, sec, key):
        if self.config.has_option(sec, key):
            return self.config.get(sec, key)
        return ''

    def set_cfg(self, sec, key, val):
        if sec is not 'DEFAULT' and not self.config.has_section(sec):
            self.config.add_section(sec)
        self.config.set(sec, key, val)

    def get_option(self, key, default=None):
        val = self.get_cfg('DEFAULT', key)
        if val == '':
            return str(default)
        return val

    def set_option(self, key, value):
        return self.set_cfg('DEFAULT', key, str(value))

    def get_option_int(self, key, default):
        return int(self.get_option(key, default))

    def get_option_bool(self, key, default):
        return self.get_option(key, default).lower() in ("yes", "true", "t", "1")

bsmdoc = bsmdoc_config()

# lexer definition
tokens = (
    'HEADING', 'NEWPARAGRAPH', 'NEWLINE', 'WORD', 'SPACE',
    'TSTART', 'TEND', 'TCELL', 'THEAD', 'TROW',
    'RBLOCK', 'BSTART', 'BEND', 'CMD', 'EQUATION', 'INLINEEQ',
    'LISTBULLET',
    'BRACKETL', 'BRACKETR',
    'BRACEL', 'BRACER',
)

states = (
    ('fblock', 'inclusive'), # function block (parsed normally)
    ('rblock', 'exclusive'), # raw block (not parsed)
    ('equation', 'exclusive'), # equation block (not parsed)
    ('table', 'inclusive'), # table block
    ('link', 'inclusive') # link block
)

# Tokens
t_ignore = '\t'
t_rblock_ignore = ''
t_equation_ignore = ''

# input stack to support dynamically changing the input text (e.g., include)
lex_input_stack = []
def t_error(t):
    print("Illegal character '%s' at line %d"%(t.value[0], t.lexer.lineno))
    t.lexer.skip(1)

def t_eof(t):
    if len(lex_input_stack):
        s = lex_input_stack.pop()
        t.lexer.input(s['lexdata'])
        t.lexer.lexpos = s['lexpos']
        t.lexer.lineno = s['lineno']
        bsmdoc.set_cfg('bsmdoc', 'filename', s['filename'])
        return t.lexer.token()
    return None

# ply uses separate eof function for each state, the default is None.
# define dummy functions to return to the up-level correctly (e.g., include,
# makecontent)
t_fblock_eof = t_eof
t_link_eof = t_eof
t_table_eof = t_eof

def bsmdoc_include(data):
    filename = data.strip()
    if os.path.isfile(filename):
        return (filename, bsmdoc_readfile(filename))
    return None

def bsmdoc_makecontent(contents):
    """
    contents is a list, where each item has four members:
    [level, pre, text, label]
        level: 1~6
        pre: the prefix (e.g., heading number)
        text: the caption text
        label: the anchor destination
    """
    if not contents:
        return ""
    first_level = 6
    # find the smallest level
    for c in contents:
        if c[0] < first_level:
            first_level = c[0]
    ctxt = []
    for c in contents:
        # the text has been parsed, so ignore the parsing here
        s = '[#%s|{%%%s %s%%}]'%(c[3], c[1], c[2])
        ctxt.append('-'*(c[0] - first_level + 1) + s)
    return '\n'.join(ctxt)

def t_INCLUDE(t):
    r'\#include[ ]+[^\s]+[\s]*'
    filename = t.value.strip()
    filename = filename.replace('#include', '', 1)
    data = bsmdoc_include(filename)
    if data is not None:
        lex_input_stack.append({'lexdata':t.lexer.lexdata,
                                'lexpos':t.lexer.lexpos,
                                'lineno': t.lexer.lineno,
                                'filename': bsmdoc.get_cfg('bsmdoc', 'filename')})
        t.lexer.input(data[1])
        t.lexer.lineno = 1
        bsmdoc.set_cfg('bsmdoc', 'filename', data[0])
        return t.lexer.token()
    else:
        print("can't not find %s"%filename)

def t_MAKECONTENT(t):
    r'\#makecontent[ ]*'
    c = bsmdoc.contents#bsmdoc.get_cfg('bsmdoc', 'CONTENT')
    if c:
        content = bsmdoc_makecontent(c)
        lex_input_stack.append({'lexdata':t.lexer.lexdata,
                                'lexpos':t.lexer.lexpos,
                                'lineno': t.lexer.lineno,
                                'filename': bsmdoc.get_cfg('bsmdoc', 'filename')})
        t.lexer.input(content)
        t.lexer.lineno = 1
        bsmdoc.set_cfg('bsmdoc', 'filename', 'CONTENT')
        return t.lexer.token()
    else:
        # if first scan, request the 2nd scan
        if bsmdoc.scan == 1:
            bsmdoc.rescane = True

# comment starts with "#", except "&#"
def t_COMMENT(t):
    r'(?<!\&)\#.*'
    pass

def t_HEADING(t):
    r'^[ ]*[\=]+[ ]*'
    t.value = t.value.strip()
    return t

def t_LISTBULLET(t):
    r'^[ ]*[\-\*]+[ ]*'
    t.value = t.value.strip()
    return t

# shortcut to define the latex equations, does not support nested statement
def t_EQN(t):
    r'\$\$'
    t.lexer.equation_start = t.lexer.lexpos
    t.lexer.push_state('equation')

def t_equation_EQN(t):
    r'\$\$'
    t.value = t.lexer.lexdata[t.lexer.equation_start:t.lexer.lexpos-2]
    t.type = 'EQUATION'
    t.lexer.lineno += t.value.count('\n')
    t.lexer.pop_state()
    return t

# everything except '$$'
def t_equation_WORD(t):
    r'(?:\\.|(\$(?!\$))|[^\$])+'
    t.lexer.lineno += t.value.count('\n')
t_equation_error = t_error

# shortcuts for inline equation
def t_INLINE_EQN(t):
    r'\$[^\$]*\$'
    t.type = 'INLINEEQ'
    t.lexer.lineno += t.value.count('\n')
    t.value = t.value[1:-1]
    return t

# marks to ignore the parsing, and it supports nested statement ('{${$ $}$}') is
# valid)
def t_CSTART(t):
    r'\{\%'
    t.lexer.rblock_start = t.lexer.lexpos
    t.lexer.rblock_level = 1
    t.lexer.push_state('rblock')

def t_rblock_CSTART(t):
    r'\{\%'
    t.lexer.rblock_level += 1

def t_rblock_CEND(t):
    r'\%\}'
    t.lexer.rblock_level -= 1
    if t.lexer.rblock_level == 0:
        t.value = \
            t.lexer.lexdata[t.lexer.rblock_start:t.lexer.lexpos - len(t.value)]
        t.type = 'RBLOCK'
        t.lexer.pop_state()
        return t

# ignore '{' if it is followed by '%';
# ignore '%' if it is followed by '}'
# it still has one problem "{%{%%}" will not work; instead we can use '{! \{\% !}'
def t_rblock_WORD(t):
    r'(?:\\.|(\{(?!\%))|(\%(?!\}))|[^\{\%])+'
    t.lexer.lineno += t.value.count('\n')

t_rblock_error = t_error

# function block
def t_BSTART(t):
    r'\{\!'
    t.lexer.push_state('fblock')
    return t

def t_fblock_BEND(t):
    r'\!\}'
    t.lexer.pop_state()
    return t

# table
def t_TSTART(t):
    r'^[ ]*\{\{'
    t.lexer.push_state('table')
    return t

def t_table_TEND(t):
    r'^[ ]*\}\}'
    t.lexer.pop_state()
    return t

def t_table_THEAD(t):
    r'[\s]*\|\+'
    return t

def t_table_TROW(t):
    r'[\s]*\|\-'
    return t

def t_TCELL(t):
    r'\|'
    return t

def t_BRACEL(t):
    r'\{'
    return t

def t_BRACER(t):
    r'\}'
    return t

# link (ignore '#' in link, so [#anchor] will work)
def t_BRACKETL(t):
    r'\['
    t.lexer.push_state('link')
    return t

def t_BRACKETR(t):
    r'\]'
    t.lexer.pop_state()
    return t

#def t_link_WORD(t):
#    r'(?:\\.|(\!(?!\}))|(\%(?!\}))|[^ \%\!\n\|\{\}\[\]])+'
#    t.value = bsmdoc_escape(t.value)
#    return t
def t_link_WORD(t):
    r'(?:\\(\W)|(\!(?!\}))|(\%(?!\}))|(?<=\&)\#|[^ \$\%\!\n\|\{\}\[\]\\])+'
    t.value = bsmdoc_escape(t.value)
    #t.value = "<br>".join(t.value.split("\\n"))
    t.value = re.sub(r'(\\)(.)', r'\2', t.value)
    return t

# support the latex stylus command, e.g., \ref{}; and the command must have at
# least 2 characters
def t_CMD(t):
    r'\\(\w)+'
    return t

def t_NEWPARAGRAPH(t):
    r'\n{2,}'
    t.lexer.lineno += t.value.count('\n')
    return t

def t_NEWLINE(t):
    r'\n'
    t.lexer.lineno += t.value.count('\n')
    return t

def t_SPACE(t):
    r'[ ]+'
    return t

# default state, ignore, '!}', '%}', '|', '[', ']', '{', '}', '\n', ' ', '#', '$'
def t_WORD(t):
    r'(?:\\(\W)|(\!(?!\}))|(\%(?!\}))|(?<=\&)\#|[^ \$\%\!\#\n\|\{\}\[\]\\])+'
    t.value = bsmdoc_escape(t.value)
    #t.value = "<br>".join(t.value.split("\\n"))
    t.value = re.sub(r'(\\)(.)', r'\2', t.value)
    return t

lex.lex(reflags=re.M)



def bsmdoc_escape(data, *args, **kwargs):
    s = re.sub(r'(<)', r'&lt;', data)
    s = re.sub(r'(>)', r'&gt;', s)
    return s
def bsmdoc_unescape(data, *args, **kwargs):
    s = re.sub(r'(&lt;)', r'<', data)
    s = re.sub(r'&gt;', r'>', s)
    return s

def bsmdoc_info_(msg, **kwargs):
    lineno = kwargs.get('lineno', -1)
    filename = kwargs.get('filename', '')
    info = msg
    if lineno != -1:
        info = "%d %s"%(lineno, info)
    if filename:
        info = ' '.join([filename, info])
    print(info)

def bsmdoc_error_(msg, **kwargs):
    bsmdoc_info_('error: '+msg, **kwargs)

def bsmdoc_warning_(msg, **kwargs):
    bsmdoc_info_('warning: '+msg, **kwargs)

def bsmdoc_helper(cmds, data, default=None, lineno=-1, inline=False):
    kwargs = {'lineno': lineno, 'inline': inline,
              'filename':bsmdoc.get_cfg('bsmdoc', 'filename')}
    ldict = lex.get_caller_module_dict(1)
    fun = ldict.get('bsmdoc_'+cmds[0], 'none')
    if fun and hasattr(fun, "__call__"):
        return str(eval('fun(data, cmds[1:], **kwargs)'))
    else:
        f = 'bsmdoc_%s(%s)' %(cmds[0], ",".join(cmds[1:]))
        bsmdoc_warning_('undefined function block "%s".'%(f))
    if default:
        return default
    else:
        return data

def bsmdoc_config(data, args, **kwargs):
    try:
        if len(args) <= 0:
            bsmdoc.config.readfp(StringIO(data))
        else:
            bsmdoc.set_option(args[0], data)
    except:
        traceback.print_exc()
        bsmdoc_error_("bsmdoc_config('%s',%s)"% (data, args), **kwargs)
    return ""

# deal with the equation reference: \ref{} or \eqref{}
def bsmdoc_ref(data, args, **kwargs):
    return "\\ref{%s}"%data
bsmdoc_eqref = bsmdoc_ref

_bsmdoc_exec_rtn = ''
def bsmdoc_exec(data, args, **kwargs):
    # check if it only needs to execute the code for the first time
    if args and args[0] == "firstRunOnly" and bsmdoc.scan > 1:
        return ''
    try:
        global _bsmdoc_exec_rtn
        _bsmdoc_exec_rtn = ''
        exec(data, globals())
        return _bsmdoc_exec_rtn
    except:
        traceback.print_exc()
        bsmdoc_error_("bsmdoc_exec('%s',%s)"% (data, args), **kwargs)
    return ''

def bsmdoc_pre(data, args, **kwargs):
    if args and args[0] == 'newlineonly':
        return "<br>\n".join(data.split("\n"))
    return "<pre>%s</pre>" % data

def bsmdoc_tag(data, args, **kwargs):
    if len(args) >= 1:
        style = bsmdoc_style_(args[1:])
        return "<%s %s>%s</%s>"%(args[0], style, data, args[0])
    return data

def bsmdoc_math(data, args, **kwargs):
    if len(args) > 0 and args[0] == 'inline':
        return '$%s$'%bsmdoc_escape(data)
    else:
        return "<div class='mathjax'>\n$$%s$$\n</div>" %bsmdoc_escape(data)

def bsmdoc_div(data, args, **kwargs):
    data = data.strip()
    if not args:
        print('div block requires at least one argument')
        return data
    style = bsmdoc_style_(args)
    return '<div %s>\n%s\n</div>\n' %(style, data)

def bsmdoc_highlight(code, lang, **kwargs):
    try:
        from pygments import highlight
        from pygments.lexers import get_lexer_by_name
        from pygments.formatters import HtmlFormatter
        lexer = get_lexer_by_name(lang[0], stripall=True)
        formatter = HtmlFormatter(linenos=False, cssclass="syntax")
        # pygments will replace '&' with '&amp;', which will make the unicode
        # (e.g., &#xNNNN) shown incorrectly.
        txt = highlight(bsmdoc_unescape(code), lexer, formatter)
        txt = txt.replace('&amp;#x', '&#x')
        txt = txt.replace('&amp;lt;', '&lt;')
        return txt.replace('&amp;gt', '&gt;')
    except ImportError:
        bsmdoc_warning_("pygments package not installed.", **kwargs)
        return bsmdoc_pre(code, [])

def static_vars(**kwargs):
    def decorate(func):
        for k in kwargs:
            setattr(func, k, kwargs[k])
        return func
    return decorate

@static_vars(notes=[])
def bsmdoc_footnote(data, args, **kwargs):
    tag = len(bsmdoc_footnote.notes) + 1
    src = 'footnote-src-%d'%tag
    dec = 'footnote-%d'%tag
    # add the footnote to the list, which will show at the end of the page
    fn = '<div id="%s">%s <a href="#%s">&#8617;</a></div>'%(dec, data, src)
    bsmdoc_footnote.notes.append(fn)
    return '<a name="%s" href="#%s"><sup>%d</sup></a>'%(src, dec, tag)

@static_vars(head={}, content=[])
def bsmdoc_header(txt, level, **kwargs):
    orderheaddict = bsmdoc_header.head
    s = txt
    pre = ''
    label = bsmdoc.get_option('label', '')

    if bsmdoc.get_option_bool('heading_numbering', 0):
        start = bsmdoc.get_option_int('heading_numbering_start', 1)
        c = len(level)
        if c >= start:
            for i in range(start, c):
                pre = pre+str(orderheaddict.get(i, 1)) + '.'

            orderheaddict[c] = orderheaddict.get(c, 0) + 1
            pre = pre + str(orderheaddict[c])

            for key in orderheaddict.keys():
                if key > c:
                    orderheaddict[key] = 0
            if not label:
                label = 'sec-' + pre.replace('.', '-')
            bsmdoc_header.content.append([c, pre, s, label])
        s = pre + ' ' + s
    if label:
        bsmdoc.set_cfg('ANCHOR', label, pre)
        label = ' id="%s"'%label

    return '<h%d%s>%s</h%d>\n'%(len(level), label, s, len(level))

@static_vars(counter=0)
def image_next_tag():
    if bsmdoc.get_option_bool('image_numbering', 0):
        image_next_tag.counter += 1
        prefix = bsmdoc.get_option('image_numbering_prefix', 'Fig.')
        num = bsmdoc.get_option('image_numbering_num_prefix', '') + str(image_next_tag.counter)
        return (str(prefix) + num + '.', prefix, num)
    return ("", "", "")

def bsmdoc_style_(args, default_class=None):
    style = []
    style_class = []
    for a in args:
        if '=' not in a:
            style_class.append(a)
        else:
            style.append(a)
    if not style_class and default_class:
        style_class.append(default_class)
    if style_class:
        style.append('class="%s"'%(' '.join(style_class)))
    return ' '.join(style)

def bsmdoc_image(data, args, **kwargs):
    inline = kwargs.get('inline', False)
    style = bsmdoc_style_(args, '')
    r = '<img %s src="%s" alt="%s">'%(style, data, data)
    if inline:
        return r
    caption = bsmdoc.get_option('caption', '')
    label = bsmdoc.get_option('label', '')
    tag = ''
    if label:
        (tag, prefix, num) = image_next_tag()
        if bsmdoc.scan == 1 and bsmdoc.get_cfg('ANCHOR', label):
            bsmdoc_warning_('duplicated label %s".'%(label), **kwargs)

        bsmdoc.set_cfg('ANCHOR', label, num)
        label = 'id="%s"'%label
        tag = '<span class="tag">%s</span>'%tag
    if caption:
        caption = '<div class="caption">%s</div>'%(tag + ' ' + caption)
        r = r + '\n' + caption
    return '<div %s class="figure">%s</div>'%(label, r)

def bsmdoc_video(data, args, **kwargs):
    style = bsmdoc_style_(args, '')
    r = '<video controls %s><source src="%s">Your browser does not support the video tag.</video>'%(style, data)
    caption = bsmdoc.get_option('caption', '')
    label = bsmdoc.get_option('label', '')
    tag = ''
    if label:
        (tag, prefix, num) = image_next_tag()
        if bsmdoc.scan == 1 and bsmdoc.get_cfg('ANCHOR', label):
            bsmdoc_warning_('duplicated label %s".'%(label), **kwargs)

        bsmdoc.set_cfg('ANCHOR', label, num)
        label = 'id="%s"'%label
        tag = '<span class="tag">%s</span>'%tag

    if caption:
        caption = '<div class="caption">%s</div>'%(tag + ' ' + caption)
        r = r + '\n' + caption
    return '<div %s class="video">%s</div>'%(label, r)

@static_vars(counter=0)
def table_next_tag():
    if bsmdoc.get_option_bool('table_numbering', 0):
        table_next_tag.counter += 1
        prefix = bsmdoc.get_option('table_numbering_prefix', 'Table.')
        num = bsmdoc.get_option('table_numbering_num_prefix', '') + str(table_next_tag.counter)
        return (str(prefix) + num + '.', prefix, num)
    return ("", "", "")

def bsmdoc_table(head, body):
    if head:
        head = '<thead>%s</thead>'%head
    if body:
        body = '<tbody>%s</tbody>'%body
    label = bsmdoc.get_option('label', '')
    tag = ''
    # add the in-page link
    if label:
        (tag, prefix, num) = table_next_tag()
        bsmdoc.set_cfg('ANCHOR', label, num)
        label = 'id="%s"'%label
        tag = '<span class="tag">%s</span>'%tag
    caption = bsmdoc.get_option('caption', '')
    if caption:
        caption = '<caption>%s</caption>'%(tag + ' ' + caption)
    return '<table %s class="table">%s\n %s</table>\n'%(label, caption, head+body)

def bsmdoc_listbullet(data, args, **kwargs):
    def listbullet(stack):
        l = r = ""
        for j in range(len(t)):
            if t[j] == r'-':
                l = l + "<ul>\n"
                r = "</ul>\n" + r
            elif t[j] == r'*':
                l = l + "<ol>\n"
                r = "</ol>\n" + r
        c = ''
        while len(stack):
            item = stack.pop()
            c = "<li>%s</li>\n"%item[1]+c
        return l+c+r

    if len(data) == 0:
        return ""
    html = ""
    # the current listbullet level
    t = data[0][0]
    # hold all the items with the current level
    stack = [data[0]]
    # next item
    i = 1
    while i < len(data):
        d = data[i]
        if d[0] == t:
            # same level as the current one, add to the list
            stack.append(d)
            i = i + 1
        else:
            # the top level is the prefix, which means d is the child item of
            # the previous item
            c = os.path.commonprefix([t, d[0]])
            if c == t:
                j = i
                # the number of child items
                cnt = 0
                while c and j < len(data):
                    cj = os.path.commonprefix([data[j][0], t])
                    if cj != c or data[j][0] == t:
                        # the last child item
                        break
                    # remove the prefix
                    data[j][0] = data[j][0][len(c):]
                    cnt = cnt + 1
                    j = j+1
                # data[i:i+cnt] is data[i-1]'s children
                tmp = bsmdoc_listbullet(data[i:i+cnt], args)
                i = j
                # update the previous item text
                item = stack.pop()
                item[1] = item[1] + tmp
                stack.append(item)
            else:
                # not the prefix of the current level, which means the previous
                # listbullet ends; and start the new one

                html = html+listbullet(stack)
                stack = [d]
                t = d[0]
                i = i+1

    return html+listbullet(stack)

def bsmdoc_anchor(data, args, **kwargs):
    return '<a name="%s"><sup>&#x2693;</sup></a>'%(data)

"""
article : sections

sections : sections block
         | block

block : HEADING logicline
      | paragraph
      | table
      | BSTART sections BEND
      | BSTART blockargs sections BEND
      | RBLOCK
      | EQUATION
      | listbullet

paragraph : text NEWPARAGRAPH
          | text

blockargs : blolkargs vtext TCELL
          | vtext TCELL

table : TSTART thead tbody TEND
      | TSTART tbody TEND

tbody : tbody trow
      | trow

trow : vtext TROW rowsep

thead: vtext THEAD rowsep

rowsep : rowsep SPACE
       | rowsep NEWLINE
       | rowsep NEWPARAGRAPH
       | SPACE
       | NEWLINE
       | NEWPARAGRAPH
       | empty

listbullet : listbullet LISTBULLET logicline
           | LISTBULLET logicline

text : text logicline
     | logicline

logicline : line
          | line NEWLINE
          | bracetext
          | bracetext NEWLINE

bracetext : BRACEL sections BRACER

line : line inlineblock
     | line plaintext
     | inlineblock
     | plaintext

inlineblock: CMD
           | CMD bracetext
           | CMD BRACEL vtext sections BRACER
           | INLINEEQ
           | BRACLETL sections BRACKETL
           | BRACKETL sections TCELL sections BRACKETR

plaintext : plaintext WORD
          | plaintext SPACE
          | WORD
          | SPACE
          | empty

empty :
"""

def p_article(p):
    '''article : sections'''
    global bsmdoc
    bsmdoc.html = p[1]

def p_sections_multi(p):
    '''sections : sections block'''
    p[0] = p[1] + p[2]

def p_sections_single(p):
    '''sections : block'''
    p[0] = p[1]

def p_heading(p):
    '''block : heading_start logicline'''
    # ignore the header level 7 or higher
    if len(p[1].strip()) <= 6:
        p[0] = bsmdoc_header(p[2].strip(), p[1].strip())
    else:
        p[0] = ""
def p_heading_start(p):
    '''heading_start : HEADING'''
    global header_level
    bsmdoc.set_option('label', '')
    p[0] = p[1]
    header_level = len(fblock_state)

def p_block_paragraph(p):
    '''block : paragraph'''
    # add <P> tag to any text which is not in a function block and ended with
    # '\n'
    if len(fblock_state) == header_level and p[1].endswith('\n'):
        p[0] = '<p>%s</p>\n' %(p[1].strip())
    else:
        p[0] = p[1]
def p_paragraph_multiple(p):
    '''paragraph : text NEWPARAGRAPH'''
    if p[1]:
        p[0] = p[1]+ '\n'
        #'<p>%s</p>' %(p[1])
        #p[0] = bsmdoc_div(p[0], ['para'])
    else:
        p[0] = ''

def p_paragraph_single(p):
    '''paragraph : text'''
    p[0] = p[1]

def p_block_table(p):
    '''block : table'''
    p[0] = p[1]

def p_table_title(p):
    '''table : tstart tbody TEND'''
    p[0] = bsmdoc_table('', p[2])

def p_table(p):
    '''table : tstart thead tbody TEND'''
    p[0] = bsmdoc_table(p[2], p[3])

def p_table_start(p):
    '''tstart : TSTART'''
    bsmdoc.set_option('caption', '')
    bsmdoc.set_option('label', '')
    p[0] = ''

def p_tbody_multi(p):
    '''tbody : tbody trow'''
    p[0] = p[1] + p[2]

def p_tbody_single(p):
    '''tbody : trow'''
    p[0] = p[1]

def p_trow(p):
    '''trow : vtext TROW rowsep'''
    s = ''.join(["<td>%s</td>"%(t.strip()) for t in p[1]])
    p[0] = '<tr>\n%s\n</tr>\n' %(s)

def p_thead(p):
    '''thead : vtext THEAD rowsep'''
    # THEAD indicates the current row is header
    s = ["<th>%s</th>"%(t.strip()) for t in p[1]]
    p[0] = '<tr>\n%s\n</tr>\n' %(''.join(s))

def p_rowsep(p):
    '''rowsep : rowsep SPACE
              | rowsep NEWLINE
              | rowsep NEWPARAGRAPH
              | SPACE
              | NEWLINE
              | NEWPARAGRAPH
              | empty'''
    p[0] = ''

# function block supports embedded block, remember the current block level
# to print the error message correspondingly when error occurs.
fblock_state = []
header_level = 0
def p_block_start(p):
    """bstart : BSTART"""
    p[0] = ''
    fblock_state.append((p[1], p.lineno(1), header_level))
    bsmdoc.set_option('caption', '')
    bsmdoc.set_option('label', '')

def p_block_end(p):
    """bend : BEND"""
    global header_level
    p[0] = ''
    header_level = fblock_state[-1][2]
    fblock_state.pop()

def p_block(p):
    '''block : bstart sections bend'''
    p[0] = p[2]

def p_block_arg(p):
    '''block : bstart blockargs sections bend'''
    cmds = p[2]
    p[0] = p[3]
    for c in reversed(cmds):
        if c:
            p[0] = bsmdoc_helper(c, p[0].strip(), lineno=p.lineno(2))

def p_blockargs_multi(p):
    '''blockargs : blockargs vtext TCELL'''
    p[0] = p[1]
    p[0].append(p[2])

def p_blockargs_single(p):
    '''blockargs : vtext TCELL'''
    p[0] = [p[1]]

def p_block_raw(p):
    '''block : RBLOCK'''
    p[0] = p[1]

def p_block_eqn(p):
    '''block : EQUATION'''
    p[0] = bsmdoc_math(p[1], [])

def p_block_listbullet(p):
    '''block : listbullet'''
    p[0] = p[1]
    p[0] = bsmdoc_listbullet(p[1], [])

def p_listbullet_multi(p):
    '''listbullet : listbullet LISTBULLET logicline'''
    p[0] = p[1]
    p[0].append([(p[2].strip()), p[3]])

def p_listbullet_single(p):
    '''listbullet : LISTBULLET logicline'''
    p[0] = [[(p[1].strip()), p[2]]]

# text separated by vertical bar '|'
def p_vtext_multi(p):
    '''vtext : vtext sections TCELL'''
    p[0] = p[1]
    p[0].append(p[2].strip())

def p_vtext_single(p):
    '''vtext : sections TCELL'''
    p[0] = [p[1].strip()]

def p_text_multi(p):
    '''text : text logicline'''
    p[0] = p[1] + p[2]

def p_text_single(p):
    '''text : logicline'''
    p[0] = p[1]

def p_logicline(p):
    '''logicline : line
                 | bracetext'''
    p[0] = p[1]

def p_logicline_newline(p):
    '''logicline : line NEWLINE
                 | bracetext NEWLINE'''
    p[0] = p[1].strip()
    if p[0]:
        p[0] = p[0] + ' \n'
def p_bracetext(p):
    '''bracetext : BRACEL sections BRACER'''
    p[0] = p[2]

def p_line_multi(p):
    '''line : line plaintext
            | line inlineblock'''
    p[0] = p[1] + p[2]

def p_line(p):
    '''line : plaintext
            | inlineblock'''
    p[0] = p[1]

def p_inlineblock_cmd(p):
    """inlineblock : CMD"""
    cmd = p[1]
    if len(cmd) == 2:
        v = cmd
        v = v.replace("\\n", '<br>')
        p[0] = re.sub(r'(\\)(.)', r'\2', v)
    else:
        default = re.sub(r'(\\)(.)', r'\2', cmd)
        p[0] = bsmdoc_helper([cmd[1:]], '', default, p.lineno(1), True)

def p_inlineblock_cmd_multi(p):
    """inlineblock : CMD bracetext"""
    cmd = p[1]
    p[0] = bsmdoc_helper([cmd[1:]], p[2], lineno=p.lineno(1), inline=True)

def p_inlineblock_cmd_args(p):
    """inlineblock : CMD BRACEL vtext sections BRACER"""
    cmd = p[3]
    cmd.insert(0, p[1][1:])
    p[0] = bsmdoc_helper(cmd, p[4], lineno=p.lineno(1), inline=True)

def p_inlineblock_eqn(p):
    '''inlineblock : INLINEEQ'''
    p[0] = bsmdoc_math(p[1], ['inline'])

def p_inlineblock_link_withname(p):
    '''inlineblock : BRACKETL sections TCELL sections BRACKETR'''
    p[0] = '<a href=\'%s\'>%s</a>'%(p[2], p[4])

def p_inlineblock_link(p):
    '''inlineblock : BRACKETL sections BRACKETR'''
    s = p[2].strip()
    v = s
    if s[0] == '#':
        v = bsmdoc.get_cfg('ANCHOR', s[1:])
        if not v:
            v = s[1:]
            # do not find the anchor, wait for the 2nd scan
            if bsmdoc.scan > 1:
                kwargs = {'lineno': p.lineno(2),
                          'filename':bsmdoc.get_cfg('bsmdoc', 'filename')}
                bsmdoc_warning_("broken anchor '%s'", **kwargs)
            bsmdoc.rescan = True
    p[0] = '<a href=\'%s\'>%s</a>'%(s, v)

def p_plaintext_multi(p):
    '''plaintext : plaintext WORD
                 | plaintext SPACE'''
    p[0] = p[1] + p[2]

def p_plaintext_single(p):
    '''plaintext : WORD
                 | SPACE
                 | empty'''
    p[0] = p[1]

def p_empty(p):
    '''empty : '''
    p[0] = ''

def p_error(p):
    if len(fblock_state):
        e = fblock_state.pop()
        kwargs = {'lineno': e[1], 'filename':bsmdoc.get_cfg('bsmdoc', 'filename')}
        bsmdoc_error_("unmatched block '%s'"%(e[0]), **kwargs)
    else:
        print("error: ", p)

yacc.yacc(debug=True)

# generate the html
bsmdoc_conf = u"""
[html]
begin = <!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN"
    "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
    <html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en">
end= </html>

[header]
begin = <head>
    <meta name="generator" content="bsmdoc, see http://bsmdoc.feiyilin.com/">
    <meta http-equiv="Content-Type" content="text/html;charset=utf-8">
end = <title>%(TITLE)s</title>
    </head>
content = <link rel="stylesheet" href="bsmdoc.css" type="text/css">

[body]
begin = <body>
    <div class="layout">
end = </div>
    </body>

[footer]
begin = <div class="footer">
end = </div>
content = <div class="footer-text"> Last updated %(UPDATED)s, by
          <a href="http://bsmdoc.feiyilin.com/">bsmdoc</a> %(SOURCE)s.</div>
"""

def bsmdoc_raw(filename, encoding):
    global bsmdoc
    txt = bsmdoc_readfile(filename, encoding)
    bsmdoc.config = SafeConfigParser()
    bsmdoc.config.readfp(StringIO(bsmdoc_conf))
    bsmdoc.set_option('UPDATED', time.strftime('%Y-%m-%d %H:%M:%S %Z', time.localtime(time.time())))
    bsmdoc.scan = 1
    bsmdoc.set_option('title', '')
    bsmdoc.set_option('source', '')
    bsmdoc.set_cfg('bsmdoc', 'filename', filename)
    lex.lexer.lineno = 1
    #lex.input(txt)
    #while True:
    #    tok = lex.token()
    #    if not tok:
    #        break      # No more input
    #    print(tok)
    yacc.parse(txt, tracking=True)
    if bsmdoc.rescan:
        bsmdoc.scan += 1
        # 2nd scan to resolve the references
        image_next_tag.counter = 0
        table_next_tag.counter = 0
        bsmdoc_header.head = {}
        bsmdoc_footnote.notes = []
        if bsmdoc_header.content:
            bsmdoc.contents = bsmdoc_header.content
        bsmdoc_header.content = []
        lex.lexer.lineno = 1
        # reset all the global options
        for k, v in bsmdoc.config.items('DEFAULT'):
            if k not in ['updated', 'title', 'source']:
                bsmdoc.config.remove_option('DEFAULT', k)
        bsmdoc.config.readfp(StringIO(bsmdoc_conf))
        yacc.parse(txt, tracking=True)
    return bsmdoc

def bsmdoc_readfile(filename, encoding=None):
    if not encoding:
        try:
            # encoding is not define, try to detect it
            import chardet
            b = min(32, os.path.getsize(filename))
            raw = open(filename, 'rb').read(b)
            result = chardet.detect(raw)
            encoding = result['encoding']
        except:
            pass
    txt = ""
    fp = io.open(filename, 'r', encoding=encoding)
    txt = fp.read()
    fp.close()
    txt = txt.encode('unicode_escape')
    txt = txt.decode()
    r = re.compile(r'\\u([a-zA-Z0-9]{4})', re.M + re.S)
    m = r.search(txt)
    while m:
        qb = '&#x' + m.group(1) + ';'
        txt = txt[:m.start()] + qb + txt[m.end():]
        m = r.search(txt, m.start())
    txt = txt.encode().decode('unicode_escape')
    return txt

def bsmdoc_gen(filename, encoding=None):
    global bsmdoc
    bsmdoc_raw(filename, encoding)
    config_doc = bsmdoc.get_option('bsmdoc_conf', '')
    if config_doc:
        txt = bsmdoc_readfile(config_doc)
        bsmdoc.config.readfp(StringIO(txt))

    bsmdoc.set_option('THISFILE', os.path.basename(filename))
    html = []
    html.append(bsmdoc.get_cfg('html', 'begin'))
    # header
    html.append(bsmdoc.get_cfg('header', 'begin'))
    html.append(bsmdoc.get_cfg('header', 'content'))
    temp = bsmdoc.get_option('addcss', '')
    if temp:
        css = temp.split(' ')
        for c in css:
            html.append('<link rel="stylesheet" href="%s" type="text/css">'%c)
    temp = bsmdoc.get_option('addjs', '')
    if temp:
        js = temp.split(' ')
        for j in js:
            html.append('<script type="text/javascript" language="javascript" src="%s"></script>'%j)
    html.append(bsmdoc.get_cfg('header', 'end'))
    # body
    html.append(bsmdoc.get_cfg('body', 'begin'))
    subtitle = bsmdoc.get_option('subtitle', '')
    if subtitle:
        subtitle = '<div class="subtitle">%s</div>\n'%(subtitle)
    doctitle = bsmdoc.get_option('doctitle', '')
    if doctitle:
        doctitle = '<div class="toptitle">%s%s</div>'%(doctitle, subtitle)
    html.append(doctitle)
    html.append(bsmdoc.html)
    html.append(bsmdoc.get_cfg('footer', 'begin'))
    if len(bsmdoc_footnote.notes):
        html.append('<ol>')
        html.append(os.linesep.join(["<li>%s</li>"%x for x in bsmdoc_footnote.notes]))
        html.append('</ol>')

    if bsmdoc.get_option('source', ''):
        bsmdoc.set_option("SOURCE", '<a href="%s">(source)</a>'%filename)
    html.append(bsmdoc.get_cfg('footer', 'content'))

    html.append(bsmdoc.get_cfg('footer', 'end'))

    html.append(bsmdoc.get_cfg('body', 'end'))

    html.append(bsmdoc.get_cfg('html', 'end'))
    outname = os.path.splitext(filename)[0] + '.html'
    fp = open(outname, 'w')
    fp.write('\n'.join(html))
    fp.close()
    return outname

if __name__ == '__main__':
    for f in sys.argv[1:]:
        bsmdoc_gen(f)
