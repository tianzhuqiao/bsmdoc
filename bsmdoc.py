#!/usr/bin/env python
# Copyright (C) Tianzhu Qiao (ben.qiao@feiyilin.com).

''' History
    ==ver 0.1.1 (12/2012)
     - fix bugs
    ==Ver 0.1 (11/2012)
     - first release
'''
import sys, re, os, tempfile, time
from subprocess import *
import ConfigParser
import StringIO
import ply.lex as lex

try:
    from pygments import highlight
    from pygments.lexers import get_lexer_by_name
    from pygments.formatters import HtmlFormatter
    pygments_loaded = True
except ImportError:
    pygments_loaded = False


def bsmdoc_highlight(lang, code):
    global pygments_loaded
    if pygments_loaded:
        lexer = get_lexer_by_name(lang, stripall=True)
        formatter = HtmlFormatter(linenos=False, cssclass="syntax")
        return highlight(code, lexer, formatter)
    return code

tokens = (
    'HEADING', 'NEWLINE', 'COMMENT', 'TEXT', 'BSMCMD',
    'LISTBULLET', 'BRACEL3', 'BRACER3',
    'TABLECELL', 'TABLEROW',
    'BRACKETL', 'BRACKETR', 'BRACKETL2', 'BRACKETR2',
    'APO5', 'APO3', 'APO2', 'APO',
    'QUOTE',
    'BRACEL', 'BRACER',
    'RAWTEXT',
    'LISTDEFINITION',
    'SPACE',
    'DOLLAR',
    'MATH'
    )

states = (
    ('block', 'inclusive'),
)

# Tokens
t_ignore = "\t"
t_BRACKETL2 = "\[\["
t_BRACKETR2 = "\]\]"
t_BRACKETL = "\["
t_BRACKETR = "\]"
t_QUOTE = "\%"
t_BRACEL = r'\{'
t_BRACER = r'\}'
t_APO5 = r'\'\'\'\'\''
t_APO3 = r'\'\'\''
t_APO2 = r'\'\''
t_APO = r'\''
t_SPACE = r'[\ ]+'
t_TEXT = r'(?:\\.|[^ \$\#\n\\\|\{\}\'\[\]\%])+'
t_DOLLAR = r'\$'

t_block_TABLEROW = r'\|\|'
t_TABLECELL = r'\|'

def t_error(t):
    print("Illegal character '%s'" % t.value[0])
    t.lexer.skip(1)

def t_BSMCMD(t):
    r'\#bsmdoc\:'
    return t
def t_COMMENT(t):
    r'\#(.)*\n'
    t.lexer.lineno += t.value.count('\n')

def t_RAWTEXT(t):
    r'<raw>(.|\n)*?</raw>'
    t.lexer.lineno += t.value.count('\n')
    t.value = t.value[5:-6]
    return t
def t_MATH(t):
    r'<math>(.|\n)*?</math>'
    t.lexer.lineno += t.value.count('\n')
    t.value = t.value[6:-7]
    return t
def t_HEADING(t):
    r'^[\ ]*[\=]+'
    return t
def t_LISTBULLET(t):
    r'^[\ ]*[\-\*]+'
    return t
def t_LISTDEFINITION(t):
    r'^[\ ]*[\:]+'
    return t
def t_NEWLINE(t):
    r'\n+'
    t.lexer.lineno += len(t.value)
    return t

def t_BRACEL3(t):
    r'^[\ ]*\{\{\{'
    #print 'start',t.lexer.lineno
    t.lexer.push_state('block')
    return t
def t_block_BRACER3(t):
    r'^[\ ]*\}\}\}'
    #print t.lexer.lineno
    t.lexer.pop_state()
    return t

lex.lex(reflags=re.M)

import ply.yacc as yacc

bsmdoc = ''
orderheaddict = {}

config = ConfigParser.ConfigParser()
def bsmdoc_getcfg(sec, key):
    global config
    if config.has_option(sec, key):
        return config.get(sec, key)
    #print '%s %s not founded' %(sec,key)
    return ''
def bsmdoc_setcfg(sec, key, val):
    global config
    config.set(sec, key, val)

def get_option(key, default):
    val = bsmdoc_getcfg('DEFAULT', key)
    if val == '':
        return str(default)
    return val

def set_option(key, value):
    global config
    if key == 'config':
        config.read(value)
    else:
        bsmdoc_setcfg('DEFAULT', key, str(value))

def get_option_int(key, default):
    return int(get_option(key, default))

def get_option_bool(key, default):
    return get_option(key, default).lower() in ("yes", "true", "t", "1")

def p_article(p):
    'article : blocks'
    global bsmdoc
    p[0] = p[1]
    bsmdoc = bsmdoc + p[0]

def p_blocks0(p):
    '''blocks : blocks block'''
    p[0] = p[1] + p[2]
def p_blocks1(p):
    '''blocks : block'''
    p[0] = p[1]

def p_block(p):
    '''block : bsmcmd
             | heading
             | paragraph
             | listbullet
             | definition
             | table
             | infoblock
             | newline'''
    p[0] = p[1]

def p_bsmcmd1(p):
    '''bsmcmd : bsmcmdstart bracetext bracetext
              | bsmcmdstart bracetext bracetext NEWLINE'''
    print p[2], p[3]
    set_option(p[2], p[3])
    p[0] = ''

def p_bsmcmd0(p):
    '''bsmcmd : bsmcmdstart bracetext
              | bsmcmdstart bracetext NEWLINE'''
    set_option(p[2], '1')
    p[0] = ''
def p_bsmcmdstart(p):
    '''bsmcmdstart : BSMCMD emptyorspace'''
    pass

def p_heading(p):
    '''heading : heading_txt
               | heading_raw'''
    p[0] = p[1]

def header_helper(txt, level):
    global orderheaddict
    s = txt
    if get_option_bool('orderhead', 0):
        start = get_option_int('orderheadstart', 1)
        pre = ''
        c = len(level)
        if c >= start:
            for i in range(start, c):
                if i not in orderheaddict:
                    orderheaddict[i] = 1
                pre = pre+str(orderheaddict[i]) + '.'

            if c not in orderheaddict:
                orderheaddict[c] = 0
            orderheaddict[c] = orderheaddict[c] + 1
            pre = pre + str(orderheaddict[c]) + ' '

            for key in orderheaddict.iterkeys():
                if key > c:
                    orderheaddict[key] = 0
        s = pre + s
    return s
def p_heading1(p):
    '''heading_txt : HEADING text'''
    s = header_helper(p[2], p[1])
    p[0] = '<h%d> %s </h%d>\n' %(len(p[1]), s, len(p[1]))
def p_heading0(p):
    'heading_raw : HEADING'
    s = header_helper('', p[1])
    p[0] = '<h%d> %s </h%d>\n' %(len(p[1]), s, len(p[1]))

def p_paragraph2(p):
    '''paragraph : paragraph NEWLINE paragraph'''
    s1 = p[1]
    s2 = p[3]
    if len(p[2]) == 1:
        p[0] = s1[:-5] + s2[3:]
    else:
        p[0] = s1 + s2

def p_paragraph1(p):
    '''paragraph : paragraph NEWLINE'''
    p[0] = p[1]
##def p_paragraph1(p):
##    '''paragraph : paragraph textwithlink'''
##    s = p[1]
##    if len(s)>5 and s[-5:]=='</p>\n':
##        s = s[:-5]
##    p[0] = s + '' + p[2] + '</p>\n'

def p_paragraph0(p):
    '''paragraph : textwithlink'''
    p[0] = '<p> %s </p>\n' %(p[1])
def p_listbulletheader1(p):
    'listbulletheader : space LISTBULLET'
    p[0] = p[2]
def p_listbulletheader0(p):
    'listbulletheader : LISTBULLET'
    p[0] = p[1]

def p_listbullet3(p):
    '''listbullet : listbullet listbulletheader brace_begin blocks brace_end
                  | listbullet listbulletheader brace_begin blocks brace_end NEWLINE'''
    s0 = p[1]
    s = '<li> %s </li>\n' %(p[4])
    for i in range(0, len(p[2])):
        if p[2][-i-1] == '-':
            s = '<ul>\n%s</ul>\n' %(s)
        elif p[2][-i-1] == '*':
            s = '<ol>\n%s</ol>\n' %(s)
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
def p_listbullet2(p):
    '''listbullet : listbullet listbulletheader textwithlink NEWLINE
                  | listbullet listbulletheader textwithlink'''
    s0 = p[1]
    s = '<li> %s </li>\n' %(p[3])
    for i in range(0, len(p[2])):
        if p[2][-i-1] == '-':
            s = '<ul>\n%s</ul>\n' %(s)
        elif p[2][-i-1] == '*':
            s = '<ol>\n%s</ol>\n' %(s)
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

def p_listbullet1(p):
    '''listbullet : listbulletheader brace_begin blocks brace_end
                  | listbulletheader brace_begin blocks brace_end NEWLINE'''
    s = '<li> %s </li>\n' %(p[3])
    for i in range(0, len(p[1])):
        if p[1][-i-1] == '-':
            s = '<ul>\n%s</ul>\n' %(s)
        elif p[1][-i-1] == '*':
            s = '<ol>\n%s</ol>\n' %(s)
    p[0] = s

def p_listbullet0(p):
    '''listbullet : listbulletheader textwithlink NEWLINE
                  | listbulletheader textwithlink'''
    s = '<li> %s </li>\n' %(p[2])
    for i in range(0, len(p[1])):
        if p[1][-i-1] == '-':
            s = '<ul>\n%s</ul>\n' %(s)
        elif p[1][-i-1] == '*':
            s = '<ol>\n%s</ol>\n' %(s)
    p[0] = s

def p_definition1(p):
    '''definition : definition LISTDEFINITION bracetext bracetext'''
    p[0] = p[1][:-5]+'\n<dt>%s</dt>\n<dd>%s</dd></dl>'%(p[3], p[4])
def p_definition0(p):
    '''definition : LISTDEFINITION bracetext bracetext'''
    p[0] = '<dl>\n<dt>%s</dt>\n<dd>%s</dd></dl>'%(p[2], p[3])

# table & block
def p_beginblock(p):
    '''beginblock : BRACEL3 emptyorspace
                  | BRACEL3 emptyorspace NEWLINE'''
    pass
def p_endblock(p):
    '''endblock :  BRACER3 emptyorspace'''
    pass
def p_table_header(p):
    '''bracetext : brace_begin textwithlink brace_end emptyorspace
                 | brace_begin textwithlink brace_end emptyorspace NEWLINE'''
    p[0] = p[2]

def p_brace_begin(p):
    '''brace_begin : emptyorspace BRACEL'''
    p[0] = p[2]
def p_brace_end(p):
    '''brace_end : BRACER'''
    p[0] = p[1]
def p_infoblock2(p):
    '''infoblock : beginblock bracetext bracetext blocks endblock'''
    if p[2] == 'bsmcode' and get_option_bool('pygments_loaded', False):
        s = p[4]
        if s[:3] == '<p>' and s[-5:] == '</p>\n':
            s = s[3:-5]
        sh = bsmdoc_highlight(p[3], s)
        p[0] = sh.encode("ISO-8859-1")
    else:
        p[0] = '<div class="%s"> \n <div class="blocktitle">%s</div>\n <div class="blockcontent">\n'%(p[2], p[3]) + p[4] + '\n</div>\n</div>\n'

def p_infoblock1(p):
    '''infoblock : beginblock bracetext blocks endblock'''
    p[0] = '<div class="%s"> \n <div class="blockcontent">\n'%(p[2]) + p[3] + '\n</div>\n</div>\n'

def p_infoblock0(p):
    '''infoblock : beginblock blocks endblock'''
    p[0] = '<div class="infoblock"> \n <div class="blockcontent">\n'+ p[2] + '\n</div>\n</div>\n'

def p_table2(p):
    '''table : beginblock bracetext bracetext tablerow emptyorspace endblock'''
    p[0] = '<table class=\'%s\'>\n <caption> %s </caption>\n%s</table>\n'%(p[3], p[2], p[4])
def p_table1(p):
    '''table : beginblock bracetext tablerow emptyorspace endblock'''
    p[0] = '<table class=\'wikitable\'>\n <caption> %s </caption>\n%s</table>\n'%(p[2], p[3])

def p_table0(p):
    '''table : beginblock tablerow emptyorspace endblock'''
    p[0] = '<table class=\'wikitable\'>\n'+ p[2] +'</table>\n'

def p_tablerow1(p):
    '''tablerow : tablerow tablecells TABLEROW emptyorspace NEWLINE'''
    p[0] = p[1] + '<tr>\n%s\n</tr>\n' %(p[2])
def p_tablerow0(p):
    '''tablerow : tablecells TABLEROW emptyorspace NEWLINE'''
    #first row is the header of the table
    s = p[1]
    s = s.replace('<td>', '<th>')
    s = s.replace('</td>', '</th>')
    p[0] = '<tr>\n%s\n</tr>\n' %(s)

def p_tablecells3(p):
    '''tablecells : tablecells emptyorspace TABLECELL emptyorspace'''
    p[0] = p[1] + '\t<td></td>'
def p_tablecells2(p):
    '''tablecells : tablecells blocks TABLECELL emptyorspace'''
    s = p[2]
    if s[:3] == '<p>' and s[-5:] == '</p>\n':
        s = s[3:-5]
    p[0] = p[1] + '\t<td>%s</td>' %(s)
def p_tablecells1(p):
    '''tablecells : emptyorspace TABLECELL emptyorspace'''
    p[0] = '\t<td></td>\n'

def p_tablecells0(p):
    '''tablecells : blocks TABLECELL emptyorspace'''
    s = p[1]
    if s[:3] == '<p>' and s[-5:] == '</p>\n':
        s = s[3:-5]
    p[0] = '\t<td>%s</td>\n' %(s)

def p_textwithlink1(p):
    '''textwithlink : textwithlink text
                    | textwithlink link
                    | textwithlink image
                    | textwithlink equation'''
    p[0] = p[1] + '' + p[2]
def p_textwithlink0(p):
    '''textwithlink : text
                    | link
                    | image
                    | equation'''
    p[0] = p[1]

def p_text1(p):
    '''text : text textelement'''
    p[0] = p[1] + p[2]
def p_text0(p):
    '''text : textelement
            | italicsorbold
            | quote'''
    p[0] = p[1]
def p_textelement1(p):
    '''textelement : RAWTEXT'''
    p[0] = p[1]
def p_textelement0(p):
    '''textelement : TEXT
            | APO
            | space
            '''
    p[0] = "<br />".join(p[1].split("\\n"))
    #p[0] = p[0].replace('\\','')
    p[0] = re.sub(r'(---)', '&#8212;', p[0])
    p[0] = re.sub(r'(--)', '&#8211;', p[0])
    p[0] = re.sub(r'(\\)(.)', r'\2', p[0])

def p_link1(p):
    '''link : BRACKETL text TABLECELL text BRACKETR'''
    p[0] = '<a href=\'%s\'>%s</a>'%(p[2], p[4])
def p_link0(p):
    '''link : BRACKETL text BRACKETR'''
    p[0] = '<a href=\'%s\'>%s</a>'%(p[2], p[2])
def p_image2(p):
    '''image : BRACKETL2 text TABLECELL text TABLECELL text BRACKETR2'''
    p[0] = '<a href=\'%s\'> <img class=\'%s\' src=\'%s\' alt=\'%s\' /></a>'%(p[2], p[6], p[2], p[4])
def p_image1(p):
    '''image : BRACKETL2 text TABLECELL text BRACKETR2'''
    p[0] = '<img src=\'%s\' alt=\'%s\' />'%(p[2], p[4])
def p_image0(p):
    '''image : BRACKETL2 text BRACKETR2'''
    p[0] = '<img src=\'%s\' alt=\'%s\' />'%(p[2], p[2])

def p_italicsorbold_bold(p):
    'italicsorbold : APO2 text APO2'
    p[0] = '<b>' + p[2] + '</b>'
def p_italicsorbold_italics(p):
    'italicsorbold : APO3 text APO3'
    p[0] = '<i>' + p[2] + '</i>'
def p_italicsorbold_both(p):
    'italicsorbold : APO5 text APO5'
    p[0] = '<i><b>' + p[2] +'</b></i>'
def p_quote(p):
    'quote : QUOTE text QUOTE'
    p[0] = '<tt>' + p[2] + '</tt>'

def geneq(eq, wl):
    # First check if there is an existing file.
    eqdir = get_option('eqdir', './eqs')
    if not os.path.exists(eqdir):
        os.makedirs(eqdir)
    dpi = get_option_int('eqndpi', 130)
    outname = get_option('eqnfilepre', '') + str(abs(hash(eq)))
    eqname = os.path.join(eqdir, outname + '.png')
    eqdepths = {}
    if get_option_bool('eqncache', 1):
        try:
            dc = open(os.path.join(eqdir, '.eqdepthcache'), 'rb')
            for l in dc:
                a = l.split()
                eqdepths[a[0]] = int(a[1])
            dc.close()

            if os.path.exists(eqname) and eqname in eqdepths:
                return (eqdepths[eqname], eqname)
        except IOError:
            print 'eqdepthcache read failed.'

    # Open tex file.
    tempdir = tempfile.gettempdir()
    fd, texfile = tempfile.mkstemp('.tex', '', tempdir, True)
    basefile = texfile[:-4]
    g = os.fdopen(fd, 'wb')

    preamble = '\documentclass{article}\n'
    eqnpackages = filter(None, get_option('eqnpackages', '').split(' '))
    for p in eqnpackages:
        preamble += '\usepackage{%s}\n' % p
    #for p in f.texlines:
         #Replace \{ and \} in p with { and }.
        # XXX hack.
    #    preamble += re.sub(r'\\(?=[{}])', '', p + '\n')
    preamble += '\usepackage{amsmath}\n'
    preamble += '\pagestyle{empty}\n\\begin{document}\n'
    g.write(preamble)

    # Write the equation itself.
    if wl:
        g.write('\\begin{eqnarray*}%s\\end{eqnarray*}' % eq)
    else:
        g.write('$%s$' % eq)

    # Finish off the tex file.
    g.write('\n\\newpage\n\end{document}')
    g.close()

    exts = ['.tex', '.aux', '.dvi', '.log']
    try:
        # Generate the DVI file
        latexcmd = 'latex -file-line-error-style -interaction=nonstopmode ' + \
                 '-output-directory %s %s' % (tempdir, texfile)
        p = Popen(latexcmd, shell=True, stdout=PIPE)
        rc = p.wait()
        if rc != 0:
            for l in p.stdout.readlines():
                print '    ' + l.rstrip()
            exts.remove('.tex')
            raise Exception('latex error')

        dvifile = basefile + '.dvi'
        dvicmd = 'dvipng --freetype0 -Q 9 -z 3 --depth -q -T tight -D %i -bg Transparent -o %s %s' % (dpi, eqname, dvifile)
        # discard warnings, as well.
        p = Popen(dvicmd, shell=True, stdout=PIPE, stderr=PIPE)
        rc = p.wait()
        if rc != 0:
            print p.stderr.readlines()
            raise Exception('dvipng error')
        depth = int(p.stdout.readlines()[-1].split('=')[-1])
    finally:
        # Clean up.
        for ext in exts:
            g = basefile + ext
            if os.path.exists(g):
                os.remove(g)

    # Update the cache if we're using it.
    if get_option_bool('eqncache', 0) and eqname not in eqdepths:
        try:
            dc = open(os.path.join(eqdir, '.eqdepthcache'), 'ab')
            dc.write(eqname + ' ' + str(depth) + '\n')
            dc.close()
        except IOError:
            print 'eqdepthcache update failed.'
    return (depth, eqname)

def p_EQUATION1(p):
    '''equation : MATH'''
    eqn = p[1]
    #(depth, fullfn) = geneq(eqn, wl=True)
    #fullfn = fullfn.replace('\\', '/')
    #if get_option_bool('eqnsupport', 0):
    #    p[0] = '<img class="eqn" src=\'%s\' alt=\'%s\' />'%(fullfn, 'equation')
    #else:
    #    p[0] = eqn
    p[0] = "$$" + eqn + "$$"
def p_EQUATION0(p):
    '''equation : DOLLAR text DOLLAR'''
    eqn = p[2]
    #(depth, fullfn) = geneq(eqn, wl=False)
    #fullfn = fullfn.replace('\\', '/')
    #if get_option_bool('eqnsupport', 0):
    #    p[0] = '<img class="eqns" src=\'%s\' alt=\'%s\' />'%(fullfn, 'equation')
    #else:
    #    p[0] = eqn
    p[0] = "$" + eqn + "$"
def p_newline(p):
    'newline : NEWLINE'
    p[0] = ''

def p_emptyorspace(p):
    '''emptyorspace : space
                    | empty'''
    p[0] = ''
def p_empty0(p):
    'empty :'
    p[0] = ''

def p_space(p):
    '''space : SPACE'''
    p[0] = ' '

def p_error(p):
    print "Syntax error in input!", p

yacc.yacc()

# generate the html
def utf8conv(s, code='gb2312'):
    us = s.decode(code)
    us = repr(us)
    us = us[2:-1]
    r = re.compile(r'\\u([a-zA-Z0-9]{4})', re.M + re.S)
    m = r.search(us)
    while m:
        qb = '&#x' + m.group(1) + ''
        us = us[:m.start()] + qb + us[m.end():]

        m = r.search(us, m.start())
    us = us.decode('string_escape')
    return us

def utf8conv2(s):
    if get_option_bool('utf8conv', 0):
        return utf8conv(s, get_option('utf8convcode', 'gb2312'))
    return s

bsmdoc_conf = """
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
begin = <div id="footer"><div id="footer-text">
end = </div></div>
content = Last updated %(UPDATED)s, by <a href=\"http://bsmdoc.feiyilin.com/\">bsmdoc</a>.\
"""


def bsmdoc_raw(txt):
    global bsmdoc
    global config
    global orderheaddict
    bsmdoc = ''
    orderheaddict = {}
    config = ConfigParser.ConfigParser()
    set_option('eqnsupport', 1)
    set_option('eqndir', 'eqn')
    set_option('eqndpi', 130)
    set_option('eqnenable', 1)
    set_option('eqncache', 1)
    set_option('eqnpackage', '')
    set_option('eqnfilepre', '')
    set_option('pygments_loaded', pygments_loaded)
    set_option('source', 0)
    set_option('UPDATED', time.strftime('%Y-%m-%d %H:%M:%S %Z', time.localtime(time.time())))
    set_option('config', 'bsmdoc.cfg')

    #config.readfp(StringIO.StringIO(bsmdoc_conf))

    bsmdoc = ''
    lex.lexer.lineno = 0
    yacc.parse(txt)
    return bsmdoc

def bsmdoc_gen(filename):
    global bsmdoc
    global config
    global orderheaddict
    try:
        fp = open(filename, 'rU')
    except:
        print 'Open file (%s) failed!'%(filename)
        return

    #try:
    bsmdoc_raw(fp.read())
    #except:
    #    print 'Parse file (%s) failed!'%(filename)
    #    fp.close()
    #    return
    fp.close()
    config_doc = get_option('bsmdoc_conf', '')
    if config_doc:
        config.readfp(open(config_doc))
    else:
        config.readfp(StringIO.StringIO(bsmdoc_conf))

    set_option('THISFILE', os.path.basename(filename))
    outname = os.path.splitext(filename)[0] +'.html'
    fp = open(outname, 'w')
    fp.write(bsmdoc_getcfg('html', 'begin') + '\n')
    fp.write(bsmdoc_getcfg('header', 'begin') + '\n')

    fp.write(bsmdoc_getcfg('header', 'content') + '\n')
    temp = get_option('addcss', '')
    if temp:
        css = temp.split(' ')
        for cssitem in css:
            fp.write('<link rel="stylesheet" href="%s" type="text/css" />\n'%(cssitem))
    temp = get_option('addjs', '')
    if temp:
        js = temp.split(' ')
        for jsitem in js:
            fp.write('<script type="text/javascript" language="javascript" src="%s"></script>\n'%(jsitem))
    temp = get_option('title', '')
    print temp
    if temp:
        title = '<title>%s</title>' %(temp)
        fp.write(utf8conv2(title) + '\n')
    fp.write(bsmdoc_getcfg('header', 'end') + '\n')
    fp.write(bsmdoc_getcfg('body', 'begin') + '\n')
    subtitle = ''
    temp = get_option('subtitle', '')
    if temp:
        subtitle = '<div id="subtitle">%s</div>'%(temp)
    doctitle = ''
    temp = get_option('doctitle', '')
    if temp:
        doctitle = '<div id="toptitle">%s%s</div>'%(temp, subtitle)
    fp.write(utf8conv2(doctitle)+'\n')

    fp.write(utf8conv2(bsmdoc))
    fp.write(bsmdoc_getcfg('footer', 'begin') + '\n')
    fp.write(bsmdoc_getcfg('footer', 'content') + '\n')
    if get_option('source', 0):
        fp.write('<a href=\"'+filename +'\">source</a>.' + '\n')

    fp.write(bsmdoc_getcfg('footer', 'end') + '\n')

    fp.write(bsmdoc_getcfg('body', 'end') + '\n')

    fp.write(bsmdoc_getcfg('html', 'end') + '\n')
    fp.close()
    return outname

if __name__ == '__main__':
    bsmdoc_gen('./example.bsmdoc')
