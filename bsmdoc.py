#!python
#!/usr/bin/env python
# Tianzhu Qiao (tq@feiyilin.com).

import sys, re, os, io, time
import traceback
import six
from six.moves import configparser
from ply import lex, yacc
import click
import chardet

from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters import HtmlFormatter

class BConfig(object):
    """
    class to hold all the configurations
    """
    def __init__(self):
        self.verbose = False
        self.lex = False

        self.config = configparser.SafeConfigParser()
        self.load(bsmdoc_conf)
        self.refs = {}
        self.cites = []
        self.contents = []
        self.header = {}
        self.footnotes = []
        self._scan = 0
        self._rescan = False
        self['filename'] = 'string'
    def __getitem__(self, item):
        if isinstance(item, six.string_types):
            items = item.split(':')
            if len(items) == 1:
                return self.get_cfg('DEFAULT', items[0])
            elif len(items) == 2:
                return self.get_cfg(items[0], items[1])
        return ""

    def __setitem__(self, item, value):
        if isinstance(item, six.string_types):
            items = item.split(':')
            if len(items) == 1:
                return self.set_cfg('DEFAULT', items[0], value)
            elif len(items) == 2:
                return self.set_cfg(items[0], items[1], value)
        return ""

    def reset_options(self):
        for k, _ in self.config.items('DEFAULT'):
            self.config.remove_option('DEFAULT', k)

        self['updated'] = time.strftime('%Y-%m-%d %H:%M:%S %Z',
                                        time.localtime(time.time()))
        self['title'] = ''
        self['show_source'] = False
        self['heading_numbering'] = False
        self['heading_numbering_start'] = 1
        self['image_numbering'] = False
        self['image_numbering_prefix'] = 'Fig.'
        self['image_numbering_num_prefix'] = ''
        self['table_numbering'] = False
        self['table_numbering_prefix'] = 'Table.'
        self['table_numbering_num_prefix'] = ''
        self['image_next_tag'] = 0
        self['table_next_tag'] = 0

        self.footnotes = []
        self.contents = []
        self.header = {}
        self.cites = []

    def get_scan(self):
        return self._scan

    def request_rescan(self):
        """request for a second scan, return false if it is the 2nd scan now"""
        if self._scan == 1:
            self._rescan = True
            return True
        return False

    def get_cfg(self, sec, key):
        val = ''
        if self.config.has_option(sec, key):
            val = self.config.get(sec, key)
            if not self.config.has_option(sec, '_type_'+key):
                return val
            types = self.config.get(sec, '_type_'+key)
            if types == 'int':
                return self.config.getint(sec, key)
            elif types == 'float':
                return self.config.getfloat(sec, key)
            elif types == 'bool':
                return self.config.getboolean(sec, key)
        return val

    def set_cfg(self, sec, key, val):
        if sec != 'DEFAULT' and not self.config.has_section(sec):
            # add section if necessary
            self.config.add_section(sec)
        self.config.set(sec, key, str(val))
        types = 'string'
        if isinstance(val, bool):
            types = 'bool'
        elif isinstance(val, six.integer_types):
            types = 'int'
        elif isinstance(val, float):
            types = 'float'
        else:
            pass
        if self.config.has_option(sec, '_type_'+key):
            types_old = self.config.get(sec, '_type_'+key)
            if types != types_old:
                bsmdoc_warning_("%s:%s change type from %s to %s"
                                %(sec, key, types_old, types))
        self.config.set(sec, '_type_'+key, types)

    def load(self, txt):
        self.config.readfp(six.StringIO(txt))

class BParse(object):
    """
    class to parse the bdoc
    """
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

    def __init__(self, verbose):
        lex.lex(module=self, reflags=re.M)
        yacc.yacc(module=self, debug=True)

        self.html = ""
        self.config = BConfig()
        self.verbose = verbose
        self.filename = ""
        self._lex_input_stack = []
        self._contents = []

        # function block supports embedded block, remember the current block
        # level to print the error message correspondingly when error occurs.
        self.fblock_state = []
        self.header_fblock_level = 0

    def pop_block(self):
        if self.fblock_state:
            s, self.header_fblock_level = self.fblock_state.pop()
            return s

    def push_block(self, b):
        self.fblock_state.append((b, self.header_fblock_level))

    def _run(self, txt):
        self.config._scan += 1
        self._contents = self.config.contents
        self.config.reset_options()
        lex.lexer.lineno = 1
        yacc.parse(txt, tracking=True)

    def run(self, filename, encoding, lexonly):
        txt = bsmdoc_readfile(filename, encoding)
        self.filename = filename
        if lexonly:
            txt = bsmdoc_readfile(filename, encoding)
            # output the lexer token for debugging
            lex.input(txt)
            tok = lex.token()
            while tok:
                click.echo(tok)
                tok = lex.token()
            return
        bsmdoc_info_("first pass scan...")

        self._run(txt)
        if self.config._rescan:
            # 2nd scan to resolve the references
            bsmdoc_info_("second pass scan...")
            self._run(txt)

    def pop_input(self):
        if self._lex_input_stack:
            return self._lex_input_stack.pop()
        return None

    def push_input(self, t, txt):
        status = {'lexdata': t.lexer.lexdata, 'lexpos': t.lexer.lexpos,
                  'lineno': t.lexer.lineno, 'filename': self.filename}
        self._lex_input_stack.append(status)
        t.lexer.input(txt)
        t.lexer.lineno = 1

    def _touch(self, t):
        self.config['lineno'] = t.lexer.lineno
        return self.config

    def t_error(self, t):
        kwargs = {'filename':self.filename, 'lineno': t.lexer.lineno}
        bsmdoc_error_("Illegal character '%s'"%(t.value[0]), **kwargs)
        t.lexer.skip(1)

    def t_eof(self, t):
        fn = self.pop_input()
        if fn:
            t.lexer.input(fn['lexdata'])
            t.lexer.lexpos = fn['lexpos']
            t.lexer.lineno = fn['lineno']
            self.filename = fn['filename']
            return t.lexer.token()
        return None

    # ply uses separate eof function for each state, the default is None.
    # define dummy functions to return to the up-level correctly (e.g., include,
    # makecontent)
    t_fblock_eof = t_eof
    t_link_eof = t_eof
    t_table_eof = t_eof

    def t_INCLUDE(self, t):
        r'\#include[ ]+[^\s]+[\s]*'
        filename = t.value.strip()
        filename = filename.replace('#include', '', 1)
        txt = bsmdoc_include(filename)
        if txt is not None:
            self.push_input(t, txt)
            self.filename = filename
            return t.lexer.token()
        else:
            kwargs = {'lineno': t.lexer.lineno, 'filename': filename}
            bsmdoc_error_("can't not find %s"%filename, **kwargs)

    def t_MAKECONTENT(self, t):
        r'\#makecontent[ ]*'
        if self._contents:
            content = bsmdoc_makecontent(self._contents)
            self.push_input(t, content)
            self.filename = "CONTENTS"
            return t.lexer.token()
        else:
            self.config.request_rescan()

    # comment starts with "#", except "&#"
    def t_COMMENT(self, t):
        r'(?<!\&)\#.*'
        pass

    def t_HEADING(self, t):
        r'^[ ]*[\=]+[ ]*'
        t.value = t.value.strip()
        return t

    def t_LISTBULLET(self, t):
        r'^[ ]*[\-\*]+[ ]*'
        t.value = t.value.strip()
        return t

    # shortcut to define the latex equations, does not support nested statement
    def t_EQN(self, t):
        r'\$\$'
        t.lexer.equation_start = t.lexer.lexpos
        t.lexer.push_state('equation')

    def t_equation_EQN(self, t):
        r'\$\$'
        t.value = t.lexer.lexdata[t.lexer.equation_start:t.lexer.lexpos-2]
        t.type = 'EQUATION'
        t.lexer.lineno += t.value.count('\n')
        t.lexer.pop_state()
        return t

    # everything except '$$'
    def t_equation_WORD(self, t):
        r'(?:\\.|(\$(?!\$))|[^\$])+'
        #t.lexer.lineno += t.value.count('\n')
        pass
    t_equation_error = t_error

    # shortcuts for inline equation
    def t_INLINE_EQN(self, t):
        r'\$[^\$\n]*\$'
        t.type = 'INLINEEQ'
        t.lexer.lineno += t.value.count('\n')
        t.value = t.value[1:-1]
        return t

    # marks to ignore the parsing, and it supports nested statement ('{%{%
    # %}%}') is valid)
    def t_RSTART(self, t):
        r'\{\%'
        t.lexer.rblock_start = t.lexer.lexpos
        t.lexer.rblock_level = 1
        t.lexer.push_state('rblock')

    def t_rblock_RSTART(self, t):
        r'\{\%'
        t.lexer.rblock_level += 1

    def t_rblock_REND(self, t):
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
    def t_rblock_WORD(self, t):
        r'(?:\\.|(\{(?!\%))|(\%(?!\}))|[^\{\%])+'
        t.lexer.lineno += t.value.count('\n')

    t_rblock_error = t_error

    # function block
    def t_BSTART(self, t):
        r'\{\!'
        t.lexer.push_state('fblock')
        return t

    def t_fblock_BEND(self, t):
        r'\!\}'
        t.lexer.pop_state()
        return t

    # table
    def t_TSTART(self, t):
        r'^[ ]*\{\{'
        t.lexer.push_state('table')
        return t

    def t_table_TEND(self, t):
        r'^[ ]*\}\}'
        t.lexer.pop_state()
        return t

    def t_table_THEAD(self, t):
        r'[\s]*\|\+'
        return t

    def t_table_TROW(self, t):
        r'[\s]*\|\-'
        return t

    def t_TCELL(self, t):
        r'\|'
        return t

    def t_BRACEL(self, t):
        r'\{'
        return t

    def t_BRACER(self, t):
        r'\}'
        return t

    # link (ignore '#' in link, so [#anchor] will work)
    def t_BRACKETL(self, t):
        r'\['
        t.lexer.push_state('link')
        return t

    def t_BRACKETR(self, t):
        r'\]'
        t.lexer.pop_state()
        return t

    def t_link_WORD(self, t):
        r'(?:\\(\W)|(\!(?!\}))|(\%(?!\}))|(?<=\&)\#|[^ \$\%\!\n\|\{\}\[\]\\])+'
        t.value = bsmdoc_escape(t.value)
        #t.value = "<br>".join(t.value.split("\\n"))
        t.value = re.sub(r'(\\)(.)', r'\2', t.value)
        return t

    # support the latex stylus command, e.g., \ref{}; and the command must have at
    # least 2 characters
    def t_CMD(self, t):
        r'\\(\w)+'
        return t

    def t_NEWPARAGRAPH(self, t):
        r'\n{2,}'
        t.lexer.lineno += t.value.count('\n')
        return t

    def t_NEWLINE(self, t):
        r'\n'
        t.lexer.lineno += t.value.count('\n')
        return t

    def t_SPACE(self, t):
        r'[ ]+'
        return t

    # default state, ignore, '!}', '%}', '|', '[', ']', '{', '}', '\n', ' ', '#', '$'
    def t_WORD(self, t):
        r'(?:\\(\W)|(\!(?!\}))|(\%(?!\}))|(?<=\&)\#|[^ \$\%\!\#\n\|\{\}\[\]\\])+'
        t.value = bsmdoc_escape(t.value)
        #t.value = "<br>".join(t.value.split("\\n"))
        t.value = re.sub(r'(\\)(.)', r'\2', t.value)
        return t


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

    def p_article(self, p):
        '''article : sections'''
        self.html = p[1]

    def p_sections_multi(self, p):
        '''sections : sections block'''
        p[0] = p[1] + p[2]

    def p_sections_single(self, p):
        '''sections : block'''
        p[0] = p[1]

    def p_heading(self, p):
        '''block : heading_start logicline'''
        # ignore the header level 7 or higher
        if len(p[1].strip()) <= 6:
            p[0] = self.cmd_helper(['header', p[1].strip()], p[2].strip(),
                                                            lineno=p.lineno(1))
        else:
            p[0] = ""
    def p_heading_start(self, p):
        '''heading_start : HEADING'''
        self.config['label'] = ''
        p[0] = p[1]
        self.header_fblock_level = len(self.fblock_state)

    def p_block_paragraph(self, p):
        '''block : paragraph'''
        # add <P> tag to any text which is not in a function block and ended with
        # '\n'
        if len(self.fblock_state) == self.header_fblock_level and\
           p[1].endswith('\n'):
            p[0] = bsmdoc_tag(p[1].strip(), ['p']) + os.linesep
        else:
            p[0] = p[1]

    def p_paragraph_multiple(self, p):
        '''paragraph : text NEWPARAGRAPH'''
        if p[1]:
            p[0] = p[1] + '\n'
            #'<p>%s</p>' %(p[1])
            #p[0] = bsmdoc_div(p[0], ['para'])
        else:
            p[0] = ''

    def p_paragraph_single(self, p):
        '''paragraph : text'''
        p[0] = p[1]

    def p_block_table(self, p):
        '''block : table'''
        p[0] = p[1]

    def p_table_title(self, p):
        '''table : tstart tbody TEND'''
        p[0] = self.cmd_helper(["table"], p[2])

    def p_table(self, p):
        '''table : tstart thead tbody TEND'''
        p[0] = self.cmd_helper(["table", p[2]], p[3])

    def p_table_start(self, p):
        '''tstart : TSTART'''
        self.config['caption'] = ''
        self.config['label'] = ''
        p[0] = ''

    def p_tbody_multi(self, p):
        '''tbody : tbody trow'''
        p[0] = p[1] + p[2]

    def p_tbody_single(self, p):
        '''tbody : trow'''
        p[0] = p[1]

    def p_trow(self, p):
        '''trow : vtext TROW rowsep'''
        row = ''.join([bsmdoc_tag(t.strip(), ['td']) for t in p[1]])
        p[0] = bsmdoc_tag(row, ['tr'])

    def p_thead(self, p):
        '''thead : vtext THEAD rowsep'''
        # THEAD indicates the current row is header
        tr = ''.join([bsmdoc_tag(t.strip(), ['th']) for t in p[1]])
        p[0] = bsmdoc_tag(tr, ['tr'])

    def p_rowsep(self, p):
        '''rowsep : rowsep SPACE
                  | rowsep NEWLINE
                  | rowsep NEWPARAGRAPH
                  | SPACE
                  | NEWLINE
                  | NEWPARAGRAPH
                  | empty'''
        p[0] = ''

    def p_block_start(self, p):
        """bstart : BSTART"""
        p[0] = ''
        self.push_block((p[1], p.lineno(1)))
        self.config['caption'] = ''
        self.config['label'] = ''

    def p_block_end(self, p):
        """bend : BEND"""
        p[0] = ''
        self.pop_block()

    def p_block(self, p):
        '''block : bstart sections bend'''
        p[0] = p[2]

    def p_block_arg(self, p):
        '''block : bstart blockargs sections bend'''
        cmds = p[2]
        p[0] = p[3]
        for c in reversed(cmds):
            if not c:
                continue
            p[0] = self.cmd_helper(c, p[0].strip(), lineno=p.lineno(2))

    def p_blockargs_multi(self, p):
        '''blockargs : blockargs vtext TCELL'''
        p[0] = p[1] + [p[2]]

    def p_blockargs_single(self, p):
        '''blockargs : vtext TCELL'''
        p[0] = [p[1]]

    def p_block_raw(self, p):
        '''block : RBLOCK'''
        p[0] = p[1]

    def p_block_eqn(self, p):
        '''block : EQUATION'''
        p[0] = self.cmd_helper(["math"], p[1], lineno=p.lineno(1))

    def p_block_listbullet(self, p):
        '''block : listbullet'''
        p[0] = p[1]
        p[0] = self.cmd_helper(["listbullet"], p[1], lineno=p.lineno(1))

    def p_listbullet_multi(self, p):
        '''listbullet : listbullet LISTBULLET logicline'''
        p[0] = p[1]
        p[0].append([(p[2].strip()), p[3]])

    def p_listbullet_single(self, p):
        '''listbullet : LISTBULLET logicline'''
        p[0] = [[(p[1].strip()), p[2]]]

    # text separated by vertical bar '|'
    def p_vtext_multi(self, p):
        '''vtext : vtext sections TCELL'''
        p[0] = p[1]
        p[0].append(p[2].strip())

    def p_vtext_single(self, p):
        '''vtext : sections TCELL'''
        p[0] = [p[1].strip()]

    def p_text_multi(self, p):
        '''text : text logicline'''
        p[0] = p[1] + p[2]

    def p_text_single(self, p):
        '''text : logicline'''
        p[0] = p[1]

    def p_logicline(self, p):
        '''logicline : line
                     | bracetext'''
        p[0] = p[1]

    def p_logicline_newline(self, p):
        '''logicline : line NEWLINE
                     | bracetext NEWLINE'''
        p[0] = p[1].strip()
        if p[0]:
            p[0] = p[0] + ' \n'

    def p_bracetext(self, p):
        '''bracetext : BRACEL sections BRACER'''
        p[0] = p[2]

    def p_line_multi(self, p):
        '''line : line plaintext
                | line inlineblock'''
        p[0] = p[1] + p[2]

    def p_line(self, p):
        '''line : plaintext
                | inlineblock'''
        p[0] = p[1]

    def p_inlineblock_cmd(self, p):
        """inlineblock : CMD"""
        cmd = p[1]
        if len(cmd) == 2:
            val = cmd
            val = val.replace("\\n", '<br>')
            p[0] = re.sub(r'(\\)(.)', r'\2', val)
        else:
            default = re.sub(r'(\\)(.)', r'\2', cmd)
            p[0] = self.cmd_helper([cmd[1:]], '', default, p.lineno(1), True)

    def p_inlineblock_cmd_multi(self, p):
        """inlineblock : CMD bracetext"""
        cmd = p[1]
        p[0] = self.cmd_helper([cmd[1:]], p[2], lineno=p.lineno(1), inline=True)

    def p_inlineblock_cmd_args(self, p):
        """inlineblock : CMD BRACEL vtext sections BRACER"""
        cmd = p[3]
        cmd.insert(0, p[1][1:])
        p[0] = self.cmd_helper(cmd, p[4], lineno=p.lineno(1), inline=True)

    def p_inlineblock_eqn(self, p):
        '''inlineblock : INLINEEQ'''
        p[0] = self.cmd_helper(["math", "inline"], p[1], lineno=p.lineno(1))

    def p_inlineblock_link_withname(self, p):
        '''inlineblock : BRACKETL sections TCELL sections BRACKETR'''
        p[0] = bsmdoc_tag(p[4], ['a', 'href="%s"'%p[2]])

    def p_inlineblock_link(self, p):
        '''inlineblock : BRACKETL sections BRACKETR'''
        s = p[2].strip()
        v = s
        if s[0] == '#':
            # internal anchor
            v = self.config['ANCHOR:%s'%s[1:]]
            if not v:
                v = s[1:]
                # do not find the anchor, wait for the 2nd scan
                if not self.config.request_rescan():
                    kwargs = {'lineno': p.lineno(2), 'filename':self.filename}
                    bsmdoc_warning_("broken anchor '%s'"%v, **kwargs)
        p[0] = bsmdoc_tag(v, ['a', 'href="%s"'%s])

    def p_plaintext_multi(self, p):
        '''plaintext : plaintext WORD
                     | plaintext SPACE'''
        p[0] = p[1] + p[2]

    def p_plaintext_single(self, p):
        '''plaintext : WORD
                     | SPACE
                     | empty'''
        p[0] = p[1]

    def p_empty(self, p):
        '''empty : '''
        p[0] = ''

    def p_error(self, p):
        blk = self.pop_block()
        if blk:
            kwargs = {'lineno': blk[1], 'filename': self.filename}
            bsmdoc_error_("unmatched block '%s'"%(blk[0]), **kwargs)
        else:
            click.echo("error: ", p)

    def cmd_helper(self, cmds, data, default='', lineno=-1, inline=False):
        kwargs = {'lineno': lineno, 'inline': inline,
                  'filename': self.filename, 'cfg': self.config}
        ldict = lex.get_caller_module_dict(1)
        fun = ldict.get('bsmdoc_'+cmds[0], 'none')
        if fun and hasattr(fun, "__call__"):
            return str(eval('fun(data, cmds[1:], **kwargs)'))
        else:
            f = 'bsmdoc_%s(%s)' %(cmds[0], ",".join(cmds[1:]))
            bsmdoc_warning_('undefined function block "%s".'%(f), **kwargs)
        if default:
            return default
        return data

def bsmdoc_include(data):
    filename = data.strip()
    if os.path.isfile(filename):
        return bsmdoc_readfile(filename)
    return ""

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
    first_level = min([c[0] for c in contents])
    ctxt = []
    for c in contents:
        # the text has been parsed, so ignore the parsing here
        s = '[#%s|{%%%s %s%%}]'%(c[3], c[1], c[2])
        ctxt.append('-'*(c[0] - first_level + 1) + s)
    return os.linesep.join(ctxt)

def bsmdoc_escape(data, *args, **kwargs):
    txt = re.sub(r'(<)', r'&lt;', data)
    txt = re.sub(r'(>)', r'&gt;', txt)
    return txt

def bsmdoc_unescape(data, *args, **kwargs):
    txt = re.sub(r'(&lt;)', r'<', data)
    txt = re.sub(r'&gt;', r'>', txt)
    return txt

def bsmdoc_info_(msg, **kwargs):
    lineno = kwargs.get('lineno', -1)
    filename = kwargs.get('filename', '')
    info = msg
    if lineno != -1:
        info = "%d %s"%(lineno, info)
    if filename:
        info = ' '.join([filename, info])
    click.echo(info)

def bsmdoc_error_(msg, **kwargs):
    bsmdoc_info_('error: '+msg, **kwargs)

def bsmdoc_warning_(msg, **kwargs):
    bsmdoc_info_('warning: '+msg, **kwargs)

def bsmdoc_config(data, args, **kwargs):
    cfg = kwargs['cfg']
    if len(args) <= 0:
        # configuration as text
        bsmdoc_info_("reading configuration...")
        cfg.load(data)
    elif args[0] == 'bsmdoc_conf':
        bsmdoc_info_("read configuration from file %s..."%data)
        cfg.load(bsmdoc_readfile(data))
    else:
        if data.lower() in ['true', 'false']:
            data = data.lower() in ['true']
        else:
            try:
                data = int(data)
            except ValueError:
                try:
                    data = float(data)
                except ValueError:
                    pass
        cfg[args[0]] = data

    return ""

def bsmdoc_label(data, args, **kwargs):
    args.insert(0, 'label')
    return bsmdoc_config(data, args, **kwargs)

def bsmdoc_caption(data, args, **kwargs):
    args.insert(0, 'caption')
    return bsmdoc_config(data, args, **kwargs)

# deal with the equation reference: \ref{} or \eqref{}
def bsmdoc_eqref(data, args, **kwargs):
    return "\\ref{%s}"%data

def bsmdoc_ref(data, args, **kwargs):
    # search in links defined with \config{label|}, so we can use the same
    # syntax to add reference to images, sections, and tables.
    cfg = kwargs.get('cfg')
    v = cfg['ANCHOR:'+data]
    if v:
        return bsmdoc_tag(v, ['a', 'href="#%s"'%data])
    elif not cfg.request_rescan() and not data.startswith('eq'):
        # do not find the anchor, wait for the 2nd scan
        bsmdoc_warning_("Probably broken anchor '%s'"%data, **kwargs)
    # can not find the anchor, assume its a equation reference for now
    return bsmdoc_eqref(data, args, **kwargs)

def bsmdoc_exec(data, args, **kwargs):
    cfg = kwargs.get('cfg')
    # check if it only needs to execute the code for the 1st scan
    if args and args[0] == "firstRunOnly" and cfg.get_scan() > 1:
        return ''
    try:
        exec(data, globals())
    except:
        bsmdoc_error_("bsmdoc_exec('%s',%s)"% (data, args), **kwargs)
        traceback.print_exc()
    return ''

def bsmdoc_pre(data, args, **kwargs):
    if args and 'newlineonly' in args:
        # only replace newline with '<br>'
        return "<br>\n".join(data.split("\n"))
    return bsmdoc_tag(data, ["pre"])

def bsmdoc_tag(data, args, **kwargs):
    if len(args) >= 1:
        tag = args[0].lower()
        style = bsmdoc_style_(args[1:])
        if style:
            if tag in ['div', 'ol', 'ul', 'tr']:
                return "<{0} {1}>\n{2}\n</{0}>\n".format(args[0], style, data)
            return "<{0} {1}>{2}</{0}>".format(args[0], style, data)
        else:
            if tag in ['div', 'ol', 'ul', 'tr']:
                return "<{0}>\n{1}\n</{0}>\n".format(args[0], data)
            return "<{0}>{1}</{0}>".format(args[0], data)
    return data

def bsmdoc_math(data, args, **kwargs):
    eqn = bsmdoc_escape(data)
    if args and args[0] == 'inline':
        return '${0}$'.format(eqn)

    return bsmdoc_div('$${0}$$'.format(eqn), ['mathjax'])

def bsmdoc_div(data, args, **kwargs):
    data = data.strip()
    if not args:
        bsmdoc_warning_('div block requires at least one argument', **kwargs)
        return data
    return bsmdoc_tag(data, ['div'] + args)

def bsmdoc_highlight(code, lang, **kwargs):
    lexer = get_lexer_by_name(lang[0], stripall=True)
    formatter = HtmlFormatter(linenos=False, cssclass="syntax")
    # pygments will replace '&' with '&amp;', which will make the unicode
    # (e.g., &#xNNNN) shown incorrectly.
    txt = highlight(bsmdoc_unescape(code), lexer, formatter)
    txt = txt.replace('&amp;#x', '&#x')
    txt = txt.replace('&amp;lt;', '&lt;')
    return txt.replace('&amp;gt', '&gt;')

def bsmdoc_cite(data, args, **kwargs):
    cfg = kwargs.get('cfg')
    hide = args and args[0] == 'hide'
    ref = cfg.refs.get(data, '')
    if not ref:
        if not cfg.request_scan():
            bsmdoc_error_("Can't find the reference: %s"%data, **kwargs)
        return ""
    i = 0
    for i in xrange(len(cfg.cites)):
        if ref == cfg.cites[i][2]:
            if hide:
                break
            cfg.cites[i][3] += 1
            ach = cfg.cites[i][3]
            tag = cfg.cites[i][1]
            break
    else:
        tag = len(cfg.cites) + 1
        ach = 1
        if hide:
            ach = 0
        cfg.cites.append(['', tag, ref, ach])
        i = -1
    src_t = 'cite_src-%d-'%(tag)
    src = '%s%d'%(src_t, ach)
    dec = 'cite-%d'%tag
    # add the reference to the list, which will show at the end of the page
    src_a = ' '.join([bsmdoc_tag('&#8617;', ['a', 'href="#%s%d"'%(src_t, a)]) for a in xrange(1, ach+1)])
    fn = bsmdoc_tag(ref+' '+ src_a, ['div', 'id="%s"'%dec])
    cfg.cites[i][0] = fn
    if hide:
        # hide the cite
        ach = ""
    else:
        ach = bsmdoc_tag(tag, ['a', 'id="%s"'%src, 'href="#%s"'%dec])
        ach = '[{0}]'.format(ach)
    return ach

def bsmdoc_reference(data, args, **kwargs):
    cfg = kwargs['cfg']
    if not args:
        bsmdoc_error_("Invalid reference definition: missing alias", **kwargs)
    k = args[0].strip()
    cfg.refs[k] = data
    return ""

def bsmdoc_footnote(data, args, **kwargs):
    cfg = kwargs['cfg']
    tag = len(cfg.footnotes) + 1
    src = 'footnote_src-%d'%tag
    dec = 'footnote-%d'%tag
    # add the footnote to the list, which will show at the end of the page
    data = data + ' ' + bsmdoc_tag('&#8617;', ['a', 'href="#%s"'%(src)])
    fn = bsmdoc_div(data, ['id="%s"'%dec])
    cfg.footnotes.append(fn)
    tag = bsmdoc_tag(tag, ['sup'])
    return bsmdoc_tag(tag, ['a', 'name="%s"'%src, 'href="#%s"'%dec])

def bsmdoc_header(txt, level, **kwargs):
    cfg = kwargs['cfg']
    orderheaddict = cfg.header
    s = txt
    pre = ''
    label = cfg['label']
    level = level[0]
    if cfg['heading_numbering']:
        start = cfg['heading_numbering_start']
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
            cfg.contents.append([c, pre, s, label])
        s = pre + ' ' + s
    if label:
        cfg['ANCHOR:%s'%label] = pre
        label = 'id="%s"'%label

    return bsmdoc_tag(s, ['h%d'%len(level), label])+'\n'

def image_next_tag(**kwargs):
    cfg = kwargs['cfg']
    if cfg['image_numbering']:
        cfg['image_next_tag'] += 1
        prefix = cfg['image_numbering_prefix']
        num = cfg['image_numbering_num_prefix'] + str(cfg['image_next_tag'])
        return (str(prefix) + num + '.', prefix, num)
    return ("", "", "")

def bsmdoc_style_(args, default_class=None):
    style = []
    style_class = []
    for a in args:
        if not a:
            continue
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
    cfg = kwargs.get('cfg')
    inline = kwargs.get('inline', False)
    style = bsmdoc_style_(args, '')
    r = '<img %s src="%s" alt="%s">'%(style, data, data)
    if inline:
        return r
    caption = cfg['caption']
    label = cfg['label']
    tag = ''
    if label:
        (tag, _, num) = image_next_tag(**kwargs)
        if cfg.get_scan() == 1 and cfg['ANCHOR%s:'%label]:
            bsmdoc_warning_('duplicated label "%s".'%(label), **kwargs)

        cfg['ANCHOR:%s'%label] = num
        label = 'id="%s"'%label
        tag = bsmdoc_tag(tag, ['span', 'tag'])
    if caption:
        caption = bsmdoc_tag(tag + ' ' + caption, ['div', "caption"])
        r = r + '\n' + caption
    return bsmdoc_tag(r, ['div', label, 'figure'])

def bsmdoc_video(data, args, **kwargs):
    cfg = kwargs['cfg']
    style = bsmdoc_style_(args, '')
    fmt = ('<video controls %s><source src="%s">'
           'Your browser does not support the video tag.</video>')
    r = fmt%(style, data)
    caption = cfg['caption']
    label = cfg['label']
    tag = ''
    if label:
        (tag, _, num) = image_next_tag(**kwargs)
        if cfg.get_scan() == 1 and cfg['ANCHOR:'+label]:
            bsmdoc_warning_('duplicated label %s".'%(label), **kwargs)

        cfg['ANCHOR:%s'%label] = num
        label = 'id="%s"'%label
        tag = '<span class="tag">%s</span>'%tag

    if caption:
        caption = '<div class="caption">%s</div>'%(tag + ' ' + caption)
        r = r + '\n' + caption
    return '<div %s class="video">%s</div>'%(label, r)

def table_next_tag(**kwargs):
    cfg = kwargs['cfg']
    if cfg['table_numbering']:
        cfg['table_next_tag'] += 1
        prefix = cfg['table_numbering_prefix']
        num = cfg['table_numbering_num_prefix'] + str(cfg['table_next_tag'])
        return (str(prefix) + num + '.', prefix, num)
    return ("", "", "")

def bsmdoc_table(body, head, **kwargs):
    cfg = kwargs['cfg']
    if head:
        head = bsmdoc_tag(head[0], ['thead'])
    else:
        head = ""
    if body:
        body = bsmdoc_tag(body, ['tbody'])

    label = cfg['label']
    tag = ''
    # add the in-page link
    if label:
        (tag, prefix, num) = table_next_tag(**kwargs)
        cfg['ANCHOR:%s'%label] = num
        label = 'id="%s"'%label
        tag = bsmdoc_tag(tag, ['span', 'tag'])
    caption = cfg['caption']
    if caption:
        caption = bsmdoc_tag(tag + ' ' + caption, ['caption'])
    tbl = bsmdoc_tag(caption+'\n '+head+body, ['table', label])
    return bsmdoc_div(tbl, ['tables'])

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
            c = bsmdoc_tag(item[1], ["li"]) + '\n' + c
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
    return bsmdoc_tag("<sup>&#x2693;</sup>", ['a', 'name="%s"'%data])

def bsmdoc_readfile(filename, encoding=None):
    if not encoding:
        try:
            # encoding is not define, try to detect it
            raw = open(filename, 'rb').read()
            result = chardet.detect(raw)
            encoding = result['encoding']
        except IOError:
            traceback.print_exc()
            return ""
    bsmdoc_info_("open \"%s\" with encoding \"%s\""%(filename, encoding))
    txt = ""
    fp = io.open(filename, 'r', encoding=encoding)
    txt = fp.read()
    fp.close()
    txt = txt.encode('unicode_escape')
    txt = txt.decode()
    regexp = re.compile(r'\\u([a-zA-Z0-9]{4})', re.M + re.S)
    m = regexp.search(txt)
    while m:
        qb = '&#x' + m.group(1) + ';'
        txt = txt[:m.start()] + qb + txt[m.end():]
        m = regexp.search(txt, m.start())
    txt = txt.encode().decode('unicode_escape')
    return txt

# generate the html
bsmdoc_conf = u"""
[html]
begin = <!doctype html"
    <html lang="en">
end= </html>

[header]
begin = <head>
    <meta name="generator" content="bsmdoc, see http://bsmdoc.feiyilin.com/">
    <meta http-equiv="Content-Type" content="text/html;charset=utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
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

class Bdoc(object):
    """class to generate the html file"""
    def __init__(self, lexonly, verbose):
        self.verbose = verbose
        self.lexonly = lexonly

    def bsmdoc_gen(self, filename, encoding=None):
        parser = BParse(verbose=self.verbose)
        parser.run(filename, encoding, self.lexonly)
        if self.lexonly:
            exit(0)
        cfg = parser.config
        cfg['THISFILE'] = os.path.basename(filename)

        html = []
        html.append(cfg['html:begin'])
        # header
        html.append(cfg['header:begin'])
        html.append(cfg['header:content'])
        for c in cfg['addcss'].split(' '):
            if not c:
                continue
            html.append('<link rel="stylesheet" href="%s" type="text/css">'%c)
        for j in cfg['addjs'].split(' '):
            if not j:
                continue
            html.append(bsmdoc_tag('', ['script', 'type="text/javascript"',
                                        'language="javascript"', 'src="%s"'%j]))
        html.append(cfg['header:end'])
        # body
        html.append(cfg['body:begin'])
        subtitle = cfg['subtitle']
        if subtitle:
            subtitle = bsmdoc_tag(subtitle, ['div', 'subtitle'])
        doctitle = cfg['doctitle']
        if doctitle:
            doctitle = bsmdoc_tag(doctitle+subtitle, ['div', 'toptitle'])
        html.append(doctitle)
        html.append(parser.html)
        # reference
        if cfg.cites:
            cites = [bsmdoc_tag(x[0], ['li']) for x in cfg.cites]
            cites = bsmdoc_tag(os.linesep.join(cites), ['ol'])
            cites = bsmdoc_tag(cites, ['div', 'reference'])
            html.append(cites)

        html.append(cfg['footer:begin'])
        if cfg.footnotes:
            foots = [bsmdoc_tag(x, ['li']) for x in cfg.footnotes]
            foots = bsmdoc_tag(os.linesep.join(foots), ['ol'])
            foots = bsmdoc_tag(foots, ['div', 'footnote'])
            html.append(foots)

        cfg["source"] = ''
        if cfg['show_source']:
            cfg["source"] = bsmdoc_tag('(source)', ['a', 'href="%s"'%filename])
        html.append(cfg['footer:content'])
        html.append(cfg['footer:end'])

        html.append(cfg['body:end'])

        html.append(cfg['html:end'])
        outname = os.path.splitext(filename)[0] + '.html'
        with open(outname, 'w') as fp:
            fp.write(os.linesep.join(html))

@click.command()
@click.option('--lex', is_flag=True, help="Show lexer output and exit.")
@click.option('--encoding', help="Set the input file encoding, e.g. 'utf-8'.")
@click.option('--verbose', is_flag=True)
@click.argument('filename', type=click.Path(exists=True))
def cli(filename, lex, encoding, verbose):
    bsmdoc = Bdoc(lex, verbose)
    bsmdoc.bsmdoc_gen(click.format_filename(filename), encoding)

if __name__ == '__main__':
    cli()
