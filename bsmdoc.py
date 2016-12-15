#!/usr/bin/env python
# Copyright (C) Tianzhu Qiao (tianzhu.qiao@feiyilin.com).

import sys, re, os, io, time
import traceback
try:
    from configparser import ConfigParser
    from io import StringIO
except ImportError:
    from ConfigParser import ConfigParser  # ver. < 3.0
    from StringIO import StringIO

import ply.lex as lex
import ply.yacc as yacc


tokens = (
    'HEADING', 'NEWPARAGRAPH', 'NEWLINE', 'CFG', 'WORD', 'SPACE',
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
        return t.lexer.token()
    return None

# ply uses separate eof function for each state, the default is None.
# define dummy functions to return to the up-level correctly (e.g., include,
# makecontent)
t_fblock_eof = t_eof
t_link_eof = t_eof
t_table_eof = t_eof

# CFG should be checked before COMMENT
def t_CFG(t):
    r'\#cfg\:(\s)*'
    return t

def t_INCLUDE(t):
    r'\#include[ ]+[^\s]+ [ ]*'
    filename = t.value.strip()
    filename = filename.replace('#include', '', 1)
    filename = filename.strip()
    if os.path.isfile(filename):
        lex_input_stack.append({'lexdata':t.lexer.lexdata,
                                'lexpos':t.lexer.lexpos,
                                'lineno': t.lexer.lineno})
        t.lexer.input(bsmdoc_readfile(filename))
        return t.lexer.token()

def t_MAKECONTENT(t):
    r'\#makecontent[ ]*'
    c = bsmdoc_getcfg('bsmdoc', 'CONTENT')
    if c:
        lex_input_stack.append({'lexdata':t.lexer.lexdata,
                                'lexpos':t.lexer.lexpos,
                                'lineno': t.lexer.lineno})
        t.lexer.input(c)
        return t.lexer.token()
    else:
        # if first scan, request the 2nd scan
        if get_option_int('scan', 1) == 1:
            set_option('rescan', True)

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

def t_link_WORD(t):
    r'(?:\\.|(\!(?!\}))|(\%(?!\}))|[^ \%\!\n\|\{\}\[\]])+'
    t.value = bsmdoc_escape(t.value)
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

bsmdoc = ''
def bsmdoc_escape(data, *args):
    s = re.sub(r'(<)', r'&lt;', data)
    s = re.sub(r'(>)', r'&gt;', s)
    return s

def bsmdoc_helper(cmds, data, default=None):
    ldict = lex.get_caller_module_dict(1)
    fun = ldict.get('bsmdoc_'+cmds[0], 'none')
    if fun and hasattr(fun, "__call__"):
        return str(eval('fun(data, cmds[1:])'))
    else:
        print('Warning: cannot find function "bsmdoc_%s(%s)".'%(cmds[0], ",".join(cmds[1:])))
    if default:
        return default
    else:
        return data

# deal with the equation reference: \ref{} or \eqref{}
def bsmdoc_ref(data, args):
    return "\\ref{%s}"%data
bsmdoc_eqref = bsmdoc_ref

def bsmdoc_exec(data, args):
    try:
        exec(data, globals())
    except:
        print(args, data)
        traceback.print_exc()
    return ''

def bsmdoc_pre(data, args):
    if args and args[0] == 'newlineonly':
        return "<br>\n".join(data.split("\n"))
    return "<pre>%s</pre>" % data

def bsmdoc_tag(data, args):
    if len(args) > 1:
        return "<%s class='%s'>%s</%s>"%(args[0], ' '.join(args[1:]), data, args[0])
    elif len(args) == 1:
        return "<%s>%s</%s>"%(args[0], data, args[0])
    return data

def bsmdoc_math(data, args):
    if len(args) > 0 and args[0] == 'inline':
        return '$%s$'%data
    else:
        return "<div class='mathjax'>\n$$ %s $$\n</div>" %bsmdoc_escape(data)

def bsmdoc_div(data, args):
    data = data.strip()
    if not args:
        print('div block requires at least one argument')
        return data
    return '<div class="%s">\n%s\n</div>\n' %(" ".join(args), data)

def bsmdoc_highlight(code, lang):
    try:
        from pygments import highlight
        from pygments.lexers import get_lexer_by_name
        from pygments.formatters import HtmlFormatter
        lexer = get_lexer_by_name(lang[0], stripall=True)
        formatter = HtmlFormatter(linenos=False, cssclass="syntax")
        # pygments will replace '&' with '&amp;', which will make the unicode
        # (e.g., &#xNNNN) shown incorrectly.
        txt = highlight(code, lexer, formatter)
        txt = txt.replace('&amp;#x', '&#x')
        txt = txt.replace('&amp;lt;', '&lt;')
        return txt.replace('&amp;gt', '&gt;')
    except ImportError:
        return code



def static_vars(**kwargs):
    def decorate(func):
        for k in kwargs:
            setattr(func, k, kwargs[k])
        return func
    return decorate

@static_vars(notes=[])
def bsmdoc_footnote(data, args):
    tag = len(bsmdoc_footnote.notes) + 1
    src = 'footnote-src-%d'%tag
    dec = 'footnote-%d'%tag
    # add the footnote to the list, which will show at the end of the page
    fn = '<div id="%s">%s <a href="#%s">&#8617;</a></div>'%(dec, data, src)
    bsmdoc_footnote.notes.append(fn)
    return '<a name="%s" href="#%s"><sup>%d</sup></a>'%(src, dec, tag)

@static_vars(head={}, content=[])
def bsmdoc_header(txt, level):
    orderheaddict = bsmdoc_header.head
    s = txt
    pre = ''
    label = get_option('label', '')

    if get_option_bool('head_tag', 0):
        start = get_option_int('head_tag_start', 1)
        c = len(level)
        if c >= start:
            for i in range(start, c):
                pre = pre+str(orderheaddict.get(i, 1)) + '.'

            orderheaddict[c] = orderheaddict.get(c, 0) + 1
            pre = pre + str(orderheaddict[c])

            for key in orderheaddict.iterkeys():
                if key > c:
                    orderheaddict[key] = 0
            if not label:
                label = 'sec-' + pre.replace('.', '-')
            bsmdoc_header.content.append([c, pre, s, label])
        s = pre + ' ' + s
    if label:
        bsmdoc_setcfg('ANCHOR', label, pre)
    return (s, pre, label)

@static_vars(counter=0)
def image_next_tag():
    if get_option_bool('image_tag', 0):
        image_next_tag.counter += 1
        prefix = get_option('image_tag_prefix', 'Fig.')
        num = get_option('image_tag_num_prefix', '') + str(image_next_tag.counter)
        return (str(prefix) + num + '.', prefix, num)
    return ("", "", "")
def bsmdoc_image(data, args):
    r = '<img src="%s" alt="%s" />'%(data, data)
    caption = get_option('caption', '')
    label = get_option('label', '')
    if len(args) >= 1:
        caption = args[0]
    if len(args) >= 2:
        label = args[1]
    # add the in-page link
    tag = ''
    if label:
        (tag, prefix, num) = image_next_tag()
        bsmdoc_setcfg('ANCHOR', label, num)
        label = 'id="%s"'%label
        tag = '<span class="tag">%s</span>'%tag

    if caption: # title
        caption = '<div class="caption">%s</div>'%(tag + ' ' + caption)
        r = r + '\n' + caption
    return '<div %s class="figure">%s</div>'%(label, r)

@static_vars(counter=0)
def table_next_tag():
    if get_option_bool('table_tag', 0):
        table_next_tag.counter += 1
        prefix = get_option('table_tag_prefix', 'Table.')
        num = get_option('table_tag_num_prefix', '') + str(table_next_tag.counter)
        return (str(prefix) + num + '.', prefix, num)
    return ("", "", "")
def bsmdoc_table(head, body):
    if head:
        head = '<thead>%s</thead>'%head
    if body:
        body = '<tbody>%s</tbody>'%body
    label = get_option('label', '')
    tag = ''
    # add the in-page link
    if label:
        (tag, prefix, num) = table_next_tag()
        bsmdoc_setcfg('ANCHOR', label, num)
        label = 'id="%s"'%label
        tag = '<span class="tag">%s</span>'%tag
    caption = get_option('caption', '')
    if caption:
        caption = '<caption>%s</caption>'%(tag + ' ' + caption)
    return '<table %s class="table">%s\n %s</table>\n'%(label, caption, head+body)

"""
article : sections

sections : sections section
         | section

section : heading
        | content

heading : HEADING logicline


content : content paragraph
        | content listbullet
        | content table
        | content config
        | paragraph
        | listbullet
        | table
        | listbullet
        | config

paragraph : text NEWPARAGRAPH
          | text

table : TSTART title trows TEND
      | TSTART title trows TEND NEWLINE
      | TSTART trows TEND
      | TSTART trows TEND NEWLINE

trows : trows trow
      | trow

trow : trowcontent TCELL
     | trowcontent TCELL rowsep

thead: trowcontent THEAD
     | trowcontent THEAD rowsep

rowsep : rowsep SPACE
       | rowsep NEWLINE
       | SPACE
       | NEWLINE
       | NEWPARAGRAPH

trowcontent : trowcontent  sections TCELL
            | sections TCELL

block : BSTART sections BEND
      | BSTART fblockarg sections BEND
      | RBLOCK

fblockarg : fblockarg plaintext TCELL
          | plaintext TCELL

listbullet : listbullet LISTBULLET logicline
           | LISTBULLET logicline

text : text logicline
     | logicline

logicline : line
          | line NEWLINE
          | bracetext
          | bracetext NEWLINE

bracetext : BRACLETL sections BRACLETR

line : line plaintext
     | line link
     | plaintext
     | link

plaintext : plaintext WORD
     | plaintext SPACE
     | WORD
     | SPACE
     |

link : BRACLETL text BRACKETL
     | BRACKETL text BRACEL text BRACKETR
     | BRACKETL2 text BRACKETR2
     | BRACKETL2 text BRACEL text BRACKETR2
     | BRACKETL2 text BRACEL text BRACEL text BRACKETR2

cfg : CFG BRACEL WORD BRACER bracetext NEWLINE
     | CFG BRACEL WORD BRACER
"""

def p_article(p):
    '''article : sections'''
    global bsmdoc
    bsmdoc = p[1]

def p_sections_multi(p):
    '''sections : sections section'''
    p[0] = p[1] + p[2]

def p_sections_single(p):
    '''sections : section'''
    p[0] = p[1]
def p_section(p):
    '''section : heading
               | content'''
    p[0] = p[1]

def p_heading(p):
    '''heading : heading_start logicline'''
    (s, pre, label) = bsmdoc_header(p[2], p[1].strip())
    p[0] = '<h%d id="%s">%s</h%d>\n' %(len(p[1]), label, s, len(p[1]))
def p_heading_start(p):
    '''heading_start : HEADING'''
    set_option('label', '')
    p[0] = p[1]

def p_content_multi(p):
    '''content : content paragraph
               | content listbullet
               | content table
               | content block'''
    p[0] = p[1] + p[2]

def p_content_single(p):
    '''content : paragraph
               | listbullet
               | table
               | block'''
    p[0] = p[1]

def p_paragraph_multiple(p):
    '''paragraph : text NEWPARAGRAPH'''
    if p[1]:
        p[0] = '<p> %s </p>' %(p[1])
        p[0] = bsmdoc_div(p[0], ['para']) + '\n'
    else:
        p[0] = ''

def p_paragraph_single(p):
    '''paragraph : text'''
    p[0] = p[1]

def p_table_title(p):
    '''table : tstart tbody tend'''
    p[0] = bsmdoc_table('', p[2])

def p_table(p):
    '''table : tstart thead tbody tend'''
    p[0] = bsmdoc_table(p[2], p[3])

def p_table_start(p):
    '''tstart : TSTART'''
    set_option('caption', '')
    set_option('label', '')
    p[0] = ''
def p_table_end(p):
    '''tend : TEND
            | TEND NEWLINE'''
    #set_option('caption', '')
    #set_option('label', '')
    p[0] = ''

def p_trows_multi(p):
    '''tbody : tbody trow'''
    p[0] = p[1] + p[2]

def p_trows_single(p):
    '''tbody : trow'''
    p[0] = p[1]

def p_trow(p):
    '''trow : trowcontent TROW
            | trowcontent TROW rowsep'''
    p[0] = '<tr>\n%s\n</tr>\n' %(p[1])

def p_thead(p):
    '''thead : trowcontent THEAD'''
    # THEAD indicates the current row is header
    s = p[1]
    s = s.replace('<td>', '<th>')
    s = s.replace('</td>', '</th>')
    p[0] = '<tr>\n%s\n</tr>\n' %(s)

def p_rowsep(p):
    '''rowsep : rowsep SPACE
              | rowsep NEWLINE
              | SPACE
              | NEWLINE
              | NEWPARAGRAPH'''
    p[0] = ''
def p_trowcontent_multi(p):
    '''trowcontent : trowcontent sections TCELL'''
    p[0] = p[1] + '<td>%s</td>' %(p[2])

def p_trowcontent_single(p):
    '''trowcontent : sections TCELL'''
    p[0] = '<td>%s</td>' %(p[1])

def p_fblock_cmd(p):
    """block : CMD"""
    cmd = p[1]
    if len(cmd) == 2:
        v = cmd
        v = v.replace("\\n", '<br>')
        p[0] = re.sub(r'(\\)(.)', r'\2', v)
    else:
        p[0] = bsmdoc_helper([cmd[1:]], '', re.sub(r'(\\)(.)', r'\2', cmd))

def p_fblock_cmd_multi(p):
    """block : CMD bracetext"""
    cmd = p[1]
    p[0] = bsmdoc_helper([cmd[1:]], p[2])
def p_fblock_cmd_args(p):
    """block : CMD BRACEL fblockarg BRACER bracetext"""
    cmd = p[3]
    cmd.insert(0, p[1][1:])
    p[0] = bsmdoc_helper(cmd, p[5])
fblock_state = []
def p_fblock_start(p):
    """bstart : BSTART"""
    p[0] = ''
    fblock_state.append((p[1], p.lineno(1)))
def p_fblock_end(p):
    """bend : BEND"""
    p[0] = ''
    fblock_state.pop()
def p_fblock(p):
    '''block : bstart sections bend
             | bstart sections bend NEWLINE'''
    p[0] = p[2]

def p_fblock_arg(p):
    '''block : bstart fblockargs sections bend
             | bstart fblockargs sections bend NEWLINE'''
    cmds = p[2]
    p[0] = p[3]
    for c in reversed(cmds):
        if c:
            p[0] = bsmdoc_helper(c, p[0])

def p_fblockargs_multi(p):
    '''fblockargs : fblockargs fblockarg TCELL'''
    p[0] = p[1]
    p[0].append(p[2])

def p_fblockargs_single(p):
    '''fblockargs : fblockarg TCELL'''
    p[0] = [p[1]]

def p_fblockarg_multi(p):
    '''fblockarg : fblockarg sections TCELL'''
    p[0] = p[1]
    p[0].append(p[2].strip())

def p_fblockarg_single(p):
    '''fblockarg : sections TCELL'''
    p[0] = [p[1].strip()]

def p_rblock(p):
    '''block : RBLOCK'''
    p[0] = p[1]

def p_rblock_eqn(p):
    '''block : EQUATION'''
    p[0] = bsmdoc_math(p[1], [])
def p_rblock_eqn_inline(p):
    '''block : INLINEEQ'''
    p[0] = bsmdoc_math(p[1], ['inline'])

def p_listbullet_multi(p):
    '''listbullet : listbullet LISTBULLET logicline'''
    s0 = p[1]
    s = '<li> %s </li>\n' %(p[3])
    for i in range(0, len(p[2])):
        if p[2][-i-1] == '-':
            s = '<ul>\n%s</ul>\n' %(s)
        elif p[2][-i-1] == '*':
            s = '<ol>\n%s</ol>\n' %(s)
    # merge the adjacent list
    for i in range(0, len(p[2])):
        if len(s0) < 6 or len(s) < 5:
            break
        if s0[-6:] == '</ul>\n' and s[:5] == '<ul>\n':
            s0 = s0[:-6]
            s = s[5:]
        elif s0[-6:] == '</ol>\n' and s[:5] == '<ol>\n':
            s0 = s0[:-6]
            s = s[5:]
        else:
            break
    p[0] = s0 + s

def p_listbullet_single(p):
    '''listbullet : LISTBULLET logicline'''
    s = '<li> %s </li>\n' %(p[2])
    for i in range(0, len(p[1])):
        if p[1][-i-1] == '-':
            s = '<ul>\n%s</ul>\n' %(s)
        elif p[1][-i-1] == '*':
            s = '<ol>\n%s</ol>\n' %(s)
    p[0] = s

def p_text_multi(p):
    '''text : text logicline'''
    p[0] = p[1] + p[2]

def p_text_single(p):
    '''text : logicline'''
    p[0] = p[1]

def p_logicline(p):
    '''logicline : line
                 | bracetext
                 | line NEWLINE
                 | bracetext NEWLINE'''
    p[0] = p[1]
def p_bracetext(p):
    '''bracetext : BRACEL sections BRACER'''
    p[0] = p[2]

def p_line_multi(p):
    '''line : line plaintext
            | line link
            | line block
            | line config'''
    p[0] = p[1] + p[2]

def p_line(p):
    '''line : plaintext
            | link
            | block
            | config'''
    p[0] = p[1]

def p_plaintext_multi(p):
    '''plaintext : plaintext WORD
            | plaintext SPACE'''
    p[0] = p[1] + p[2]

def p_plaintext_single(p):
    '''plaintext : WORD
            | SPACE'''
    p[0] = p[1]
def p_plaintext_empty(p):
    '''plaintext : '''
    p[0] = ''

def p_link_withname(p):
    '''link : BRACKETL text TCELL text BRACKETR'''
    p[0] = '<a href=\'%s\'>%s</a>'%(p[2], p[4])

def p_link_noname(p):
    '''link : BRACKETL text BRACKETR'''
    s = p[2].strip()
    v = s
    if s[0] == '#':
        v = bsmdoc_getcfg('ANCHOR', s[1:])
        if not v:
            v = s[1:]
            # do not find the anchor, wait for the 2nd scan
            if get_option_int('scan', 1) > 1:
                print("Broken anchor '%s' at line %d"%(s, p.lineno(2)))
            set_option('rescan', True)
    p[0] = '<a href=\'%s\'>%s</a>'%(s, v)

def p_config_multi(p):
    '''config : CFG BRACEL WORD BRACER bracetext'''
    set_option(p[3], p[5])
    p[0] = ''

def p_config_single(p):
    '''config : CFG BRACEL WORD BRACER'''
    set_option(p[3], '1')
    p[0] = ''

def p_error(p):
    if len(fblock_state):
        e = fblock_state.pop()
        print("Error: unmatched block '%s' at line %d"%(e[0], e[1]))
    else:
        print("Error: ", p)

yacc.yacc(debug=True)

# generate the html
bsmdoc_conf = u"""
[html]
begin = <!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN"
    "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
    <html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en">
end= </html>

[header]
begin = <head>
    <meta name="generator" content="bsmdoc, see http://bsmdoc.feiyilin.com/" />
    <meta http-equiv="Content-Type" content="text/html;charset=utf-8" />
end = </head>
content = <link rel="stylesheet" href="bsmdoc.css" type="text/css" />

[body]
begin = <body>
    <div id="layout-content">
end = </div>
    </body>

[footer]
begin = <div id="footer">
end = </div>
content = <div id="footer-text"> Last updated %(UPDATED)s, by
          <a href="http://bsmdoc.feiyilin.com/">bsmdoc</a> %(SOURCE)s.</div>
"""
def make_content(content):
    first_level = 6
    for c in content:
        if c[0] < first_level:
            first_level = c[0]
    ctxt = []
    # put the header in '{- -}' block, so bsmdoc will not try to parse it again
    for c in content:
        s = '<a href="#%s">%s</a>' %(c[3], c[1] + ' ' + c[2])
        # % is the variable substitution symbol in ConfigParser;
        # %% for substitution escape
        ctxt.append('-'*(c[0] - first_level + 1) + '{%'+ s + '%}')
    return '\n'.join(ctxt)
    s0 = ""
    level_pre = -1
    for c in content:
        s = '<li><a href="#%s">%s</a></li>\n' %(c[3], c[1] + ' ' + c[2])
        if level_pre == -1:
            for i in range(0, c[0] - first_level + 1):
                s = '<ul>\n%s' %(s)
        elif c[0] > level_pre:
            for i in range(0, c[0] - level_pre):
                s = '<li><ul>\n' + s
        elif c[0] < level_pre:
            for i in range(0, level_pre - c[0]):
                s = '</ul></li>\n' + s
        level_pre = c[0]
        s0 = s0 + s
    for i in range(0, level_pre - first_level):
        s0 = s0 + '</ul></li>\n'
    return s0 + '</ul>'

config = ConfigParser()
def bsmdoc_getcfg(sec, key):
    global config
    if config.has_option(sec, key):
        return config.get(sec, key)
    return ''
def bsmdoc_setcfg(sec, key, val):
    global config
    if sec is not 'DEFAULT' and not config.has_section(sec):
        config.add_section(sec)
    config.set(sec, key, val)

def get_option(key, default=None):
    val = bsmdoc_getcfg('DEFAULT', key)
    if val == '':
        return str(default)
    return val

def set_option(key, value):
    bsmdoc_setcfg('DEFAULT', key, str(value))

def get_option_int(key, default):
    return int(get_option(key, default))

def get_option_bool(key, default):
    return get_option(key, default).lower() in ("yes", "true", "t", "1")

def bsmdoc_raw(txt):
    global bsmdoc
    global config
    config = ConfigParser()
    config.add_section('ANCHOR')

    set_option('UPDATED', time.strftime('%Y-%m-%d %H:%M:%S %Z', time.localtime(time.time())))
    set_option('scan', 1)
    set_option('source', '')

    bsmdoc = ''
    lex.lexer.lineno = 1
    #lex.input(txt)
    #while True:
    #    tok = lex.token()
    #    if not tok:
    #        break      # No more input
    #    print(tok)
    yacc.parse(txt, tracking=True)
    if get_option_bool('rescan', False):
        set_option('scan', 2)
        # 2nd scan to resolve the references
        image_next_tag.counter = 0
        table_next_tag.counter = 0
        bsmdoc_header.head = {}
        bsmdoc_footnote.notes = []
        if bsmdoc_header.content:
            s = make_content(bsmdoc_header.content)
            s = s.replace('%', '%%')
            bsmdoc_setcfg('bsmdoc', 'CONTENT', s)
        bsmdoc_header.content = []
        lex.lexer.lineno = 1
        #lex.input(txt)
        #while True:
        #    tok = lex.token()
        #    if not tok:
        #        break      # No more input
        #    print(tok)
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
    global config
    txt = bsmdoc_readfile(filename, encoding)
    bsmdoc_raw(txt)
    config_doc = get_option('bsmdoc_conf', '')
    if config_doc:
        txt = bsmdoc_readfile(config_doc)
        config.readfp(StringIO(txt))
    else:
        config.readfp(StringIO(bsmdoc_conf))

    set_option('THISFILE', os.path.basename(filename))
    html = []
    html.append(bsmdoc_getcfg('html', 'begin'))
    # header
    html.append(bsmdoc_getcfg('header', 'begin'))
    html.append(bsmdoc_getcfg('header', 'content'))
    temp = get_option('addcss', '')
    if temp:
        css = temp.split(' ')
        for c in css:
            html.append('<link rel="stylesheet" href="%s" type="text/css" />'%c)
    temp = get_option('addjs', '')
    if temp:
        js = temp.split(' ')
        for j in js:
            html.append('<script type="text/javascript" language="javascript" src="%s"></script>'%j)
    temp = get_option('title', '')
    if temp:
        html.append('<title>%s</title>'%(temp))
    html.append(bsmdoc_getcfg('header', 'end') + '\n')
    # body
    html.append(bsmdoc_getcfg('body', 'begin') + '\n')
    subtitle = get_option('subtitle', '')
    if subtitle:
        subtitle = '<div id="subtitle">%s</div>\n'%(subtitle)
    doctitle = get_option('doctitle', '')
    if doctitle:
        doctitle = '<div id="toptitle">%s%s</div>'%(doctitle, subtitle)
    html.append(doctitle)

    html.append(bsmdoc)#get_option('BSMDOC'))
    html.append(bsmdoc_getcfg('footer', 'begin'))
    if len(bsmdoc_footnote.notes):
        html.append('<ol>')
        html.append(os.linesep.join(["<li>%s</li>"%x for x in bsmdoc_footnote.notes]))
        html.append('</ol>')

    if get_option('source', ''):
        set_option("SOURCE", '<a href="%s">(source)</a>'%filename)
    html.append(bsmdoc_getcfg('footer', 'content'))

    html.append(bsmdoc_getcfg('footer', 'end'))

    html.append(bsmdoc_getcfg('body', 'end'))

    html.append(bsmdoc_getcfg('html', 'end'))
    outname = os.path.splitext(filename)[0] + '.html'
    fp = open(outname, 'w')
    fp.write(os.linesep.join(html))
    fp.close()
    return outname

if __name__ == '__main__':
    for f in sys.argv[1:]:
        bsmdoc_gen(f)
