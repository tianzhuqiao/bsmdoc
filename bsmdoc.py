import sys
import re
import os
import time
import traceback
from ast import literal_eval
import six
from six.moves import configparser
from ply import lex, yacc
import click
import cchardet as chardet

from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters import HtmlFormatter

__version__ = '0.0.7'


class BConfig(object):
    """
    class to hold all the configurations
    """
    def __init__(self):
        self.config = configparser.ConfigParser(delimiters=('=', ))
        # cite & reference
        self.refs = {}
        self.cited = []
        # contents
        self.contents = []
        # the dict stores current tag for each heading level
        self.heading_tag = {}
        # footnote list
        self.footnotes = []
        # alias
        self.alias = {}
        self._scan = 0
        self._need_scan = True # at least scan once

        self.scan_info = {}

    def __getitem__(self, item):
        if isinstance(item, six.string_types):
            items = item.split(':')
            if len(items) == 1:
                return self.get_cfg('DEFAULT', items[0])
            elif len(items) >= 2:
                return self.get_cfg(items[0], ':'.join(items[1:]))
        return ""

    def __setitem__(self, item, value):
        if isinstance(item, six.string_types):
            items = item.split(':')
            if len(items) == 1:
                return self.set_cfg('DEFAULT', items[0], value)
            elif len(items) >= 2:
                return self.set_cfg(items[0], ':'.join(items[1:]), value)
        return ""

    def get_vars(self):
        if self.config.has_section('v'):
            return dict(self.config._sections['v'])
        return {}

    def set_vars(self, sec):
        self.config.remove_section('v')
        self.config.add_section('v')
        for k, v in six.iteritems(sec):
            self.config.set('v', k, v)

    def reset_options(self):
        for k, _ in self.config.items('DEFAULT'):
            self.config.remove_option('DEFAULT', k)

        self.load(bsmdoc_conf)
        self.set_updated(time.localtime(time.time()), True)
        self['title'] = ''
        self['doctitle'] = '%(TITLE)s'
        self['subtitle'] = ''
        self['show_source'] = False
        self['heading_numbering'] = False
        self['heading_numbering_start'] = 1
        self['heading_in_contents'] = True
        self['show_table_of_contents'] = False

        self['image_numbering'] = False
        self['image_numbering_prefix'] = 'Fig.'
        self['image_numbering_num_prefix'] = ''
        self['image_numbering_next_tag'] = 0

        self['video_numbering'] = 'image' # share numbering with image block
        self['video_numbering_prefix'] = 'Video.'
        self['video_numbering_num_prefix'] = ''
        self['video_numbering_next_tag'] = 0

        self['table_numbering'] = False
        self['table_numbering_prefix'] = 'Table.'
        self['table_numbering_num_prefix'] = ''
        self['table_numbering_next_tag'] = 0

        self.footnotes = []
        self.contents = []
        self.heading_tag = {}
        self.cited = []
        self.alias = {}

    def set_updated(self, t, forced=False):
        if forced or not self['updated']:
            self['updated'] = time.strftime('%Y-%m-%d %H:%M:%S %Z', t)
        else:
            ct = time.strptime(self['updated'], '%Y-%m-%d %H:%M:%S %Z')
            if ct < t:
                self['updated'] = time.strftime('%Y-%m-%d %H:%M:%S %Z', t)

    def get_scan(self) -> int:
        return self._scan

    def next_scan(self):
        self._scan += 1
        self._need_scan = False

    def need_scan(self) -> bool:
        return self._need_scan

    def request_scan(self):
        """request for a second scan, return false if it is the 2nd scan now"""
        if self._scan == 1:
            self._need_scan = True
            return True
        return False

    def reset_scan(self):
        self._scan = 0
        self._need_scan = True

    def get_cfg(self, sec, key):
        val = ''
        if self.config.has_option(sec, key):
            val = _to_literal(self.config.get(sec, key))
        return val

    def set_cfg(self, sec, key, val):
        if sec != 'DEFAULT' and not self.config.has_section(sec):
            # add section if necessary
            self.config.add_section(sec)
        self.config.set(sec, key, str(val))

    def load(self, txt):
        self.config.read_string(txt)


class BParse(object):
    """
    class to parse the bsmdoc
    """
    # lexer definition
    tokens = (
        'HEADING',
        'NEWPARAGRAPH',
        'NEWLINE',
        'WORD',
        'SPACE',
        'TSTART',
        'TEND',
        'TCELL',
        'THEAD',
        'TROW',
        'RBLOCK',
        'BSTART',
        'BEND',
        'CMD',
        'EQUATION',
        'INLINEEQ',
        'LISTBULLET',
        'BRACKETL',
        'BRACKETR',
        'BRACEL',
        'BRACER',
    )

    states = (
        ('fblock', 'inclusive'),  # function block (parsed normally)
        ('rblock', 'exclusive'),  # raw block (not parsed)
        ('equation', 'exclusive'),  # equation block (not parsed)
        ('table', 'inclusive'),  # table block
        ('link', 'inclusive')  # link block
    )

    # Tokens
    t_ignore = '\t'
    t_rblock_ignore = ''
    t_equation_ignore = ''

    def __init__(self, verbose):
        lex.lex(module=self, reflags=re.M)
        yacc.yacc(module=self, debug=verbose)

        # add function block \__version__ = __version__
        BFunction('__version__')(__version__)
        self.html = ""
        self.config = BConfig()
        self.verbose = verbose
        self.filename = ""
        self._input_stack = []
        self.contents = ''

        # function block supports embedded block, remember the current block
        # level to print the error message correspondingly when error occurs.
        self.block_state = []
        self.heading_level = 0

    def top_block(self):
        if self.block_state:
            return self.block_state[-1]
        return None

    def pop_block(self, lineno=-1):
        if self.block_state:
            args = self.block_state.pop()
            self.heading_level = args['heading_level']
            self.config.set_vars(args['config'])
            args.pop('config', None)
            args.pop('heading_level', None)
            return args
        self._error('no more blocks', lineno=lineno)
        return None

    def push_block(self, args):
        assert isinstance(args, dict)
        if args['block'] == 'heading':
            self.heading_level = len(self.block_state)
        args['heading_level'] = self.heading_level
        # save the default section in configuration, so that when leave the
        # block, the configuration in the block will not change the upper level
        args['config'] = self.config.get_vars()
        self.config.set_vars({})
        self.block_state.append(args)

    def scan(self, txt):
        # start next scan
        self.config.next_scan()
        self._info("scan %d ..." % (self.config.get_scan()))
        # save the table of contents collected from previous scan or empty for
        # 1st scan
        self.config.reset_options()
        self.config['filename'] = self.filename
        self.config['basename'] = os.path.basename(self.filename)
        if self.filename != "<input>":
            mt = time.gmtime(os.path.getmtime(self.filename))
        else:
            mt = time.gmtime()
        self.config.set_updated(mt, True)
        lex.lexer.lineno = 1
        yacc.parse(txt, tracking=True)

    def run(self, txt, filename="<input>", lex_only=False):
        self.filename = filename
        if lex_only:
            # output the lexer token for debugging
            lex.input(txt)
            for tok in lex.lexer:
                click.echo(tok)
            return None

        self.config.reset_scan()
        while self.config.need_scan():
            self.scan(txt)

        self.contents = BFunction().makecontent(self.config.contents)
        return self.html

    def pop_input(self):
        if self._input_stack:
            return self._input_stack.pop()
        return None

    def push_input(self, t, txt):
        status = {
            'lexdata': t.lexer.lexdata,
            'lexpos': t.lexer.lexpos,
            'lineno': t.lexer.lineno,
            'filename': self.filename
        }
        self._input_stack.append(status)
        t.lexer.input(txt)
        t.lexer.lineno = 1

    def _touch(self, t):
        self.config['lineno'] = t.lexer.lineno
        return self.config

    def _info(self, msg, **kwargs):
        info = self._scan_info(**kwargs)
        _bsmdoc_info(msg, **info)

    def _warning(self, msg, **kwargs):
        info = self._scan_info(**kwargs)
        _bsmdoc_warning(msg, **info)

    def _error(self, msg, **kwargs):
        info = self._scan_info(**kwargs)
        _bsmdoc_error(msg, **info)

    def _scan_info(self, **kwargs):
        info = {'silent': not self.verbose,
                'include': self.filename,
                'cfg': self.config,
                'indent': len(self._input_stack)}
        info.update(kwargs)
        # update the scan info for BFunction, so it can show the debug info
        # (ugly, TODO)
        BFunction.scan_info = dict(info)
        self.config.scan_info = dict(info)
        return info

    # lexer
    def t_error(self, t):
        self._error("illegal character '%s'" % (t.value[0]), lineno=t.lexer.lineno)
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
        r'\#include[^\S\r\n]+[\S]+[\s]*$'
        filename = t.value.strip()
        filename = filename.replace('#include', '', 1).strip()
        kwargs = self._scan_info(lineno=t.lexer.lineno)
        txt = BFunction().include(filename, **kwargs)
        t.lexer.lineno += t.value.count('\n')
        if txt:
            self.push_input(t, txt)
            self.filename = filename
            if os.path.isfile(filename):
                self.config.set_updated(time.gmtime(os.path.getmtime(filename)), False)
            return t.lexer.token()
        return None

    def t_MAKECONTENT(self, t):
        r'\#makecontent[^\S\r\n]*$'

        self.config['show_table_of_contents'] = True
        self._warning(r'#makecontent is depreciated, use \config{show_table_of_contents|True}',
                      lineno=t.lexer.lineno)

        return None

    # comment starts with "#", except "&#"
    def t_COMMENT(self, t):
        r'(?<!\&)\#.*'
        pass

    def t_HEADING(self, t):
        r'^[^\S\r\n]*[\=]+[^\S\r\n]*'
        t.value = t.value.strip()
        return t

    def t_LISTBULLET(self, t):
        r'^[^\S\r\n]*[\-\*]+[^\S\r\n]*'
        t.value = t.value.strip()
        return t

    # shortcut to define the latex equations, does not support nested statement
    def t_EQN(self, t):
        r'^[^\S\r\n]*\$\$'
        t.lexer.equation_start = t.lexer.lexpos
        t.lexer.push_state('equation')

    def t_equation_EQN(self, t):
        r'\$\$'
        t.value = t.lexer.lexdata[t.lexer.equation_start:t.lexer.lexpos - 2]
        t.type = 'EQUATION'
        t.lexer.lineno += t.value.count('\n')
        t.lexer.pop_state()
        return t

    # everything except '$$'
    def t_equation_WORD(self, t):
        r'(?:\\.|(\$(?!\$))|[^\$])+'
        pass

    t_equation_error = t_error

    # shortcuts for inline equation
    def t_INLINE_EQN(self, t):
        r'\$[^\$\n]*\$'
        t.type = 'INLINEEQ'
        t.lexer.lineno += t.value.count('\n')
        t.value = t.value[1:-1]
        return t

    def t_INLINE_EQN2(self, t):
        r'\\\([^\n]*?\\\)'
        t.type = 'INLINEEQ'
        t.lexer.lineno += t.value.count('\n')
        t.value = t.value[2:-2]
        return t

    # marks to ignore parsing, and it supports nested statement ('{%{% %}%}')
    # is valid)
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
        return None

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
        r'[^\S\r\n]*[\n]?\!\}'
        t.lexer.pop_state()
        t.lexer.lineno += t.value.count('\n')
        return t

    # table
    def t_TSTART(self, t):
        r'^[^\S\r\n]*\{\{'
        t.lexer.push_state('table')
        return t

    def t_table_TEND(self, t):
        r'^[^\S\r\n]*\}\}'
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
        t.value = BFunction().escape(t.value)
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
        r'[^\S\r\n]+'
        t.value = ' '
        return t

    def t_escape_WORD(self, t):
        r'(?:\\(\W))+'
        t.value = BFunction().escape(t.value)
        t.value = re.sub(r'(\\)(.)', r'\2', t.value)
        t.type = 'WORD'
        return t

    # default state, ignore, '!}', '%}', '|', '[', ']', '{', '}', '\n', ' ', '#', '$'
    def t_WORD(self, t):
        r'(?:(\!(?!\}))|(\%(?!\}))|(?<=\&)\#|[^ \$\%\!\#\n\|\{\}\[\]\\])+'
        t.value = BFunction().escape(t.value)
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
            p[0] = self.cmd_helper(['heading', p[1].strip()],
                                   p[2].strip(),
                                   lineno=p.lineno(1))
        else:
            p[0] = ""
        self.pop_block()

    def p_heading_start(self, p):
        '''heading_start : HEADING'''
        self.push_block({'block': 'heading', 'lineno': p.lineno(1)})
        p[0] = p[1]

    def p_block_paragraph(self, p):
        '''block : paragraph'''
        # add <P> tag to any text which is not in a function block and ended
        # with '\n
        if not p[1].strip():
            p[0] = ""
        elif len(self.block_state) == self.heading_level and p[1].endswith('\n'):
            p[0] = BFunction().tag(p[1].strip(), 'p') + '\n'
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
        self.pop_block()

    def p_table(self, p):
        '''table : tstart thead tbody TEND'''
        p[0] = self.cmd_helper(["table", p[2]], p[3])
        self.pop_block()

    def p_table_start(self, p):
        '''tstart : TSTART'''
        self.push_block({'block': 'table', 'lineno': p.lineno(1)})
        p[0] = ''

    def p_tbody_multi(self, p):
        '''tbody : tbody trow'''
        p[0] = p[1] + p[2]

    def p_tbody_single(self, p):
        '''tbody : trow'''
        p[0] = p[1]

    def p_trow(self, p):
        '''trow : vtext TROW rowsep'''
        row = ''.join([BFunction().tag(t.strip(), 'td') for t in p[1]])
        p[0] = BFunction().tag(row, 'tr')

    def p_thead(self, p):
        '''thead : vtext THEAD rowsep'''
        # THEAD indicates the current row is header
        tr = ''.join([BFunction().tag(t.strip(), 'th') for t in p[1]])
        p[0] = BFunction().tag(tr, 'tr')

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
        self.push_block({'block': 'fun', 'lineno': p.lineno(1)})

    def p_block_end(self, p):
        """bend : BEND"""
        p[0] = ''

    def p_block(self, p):
        '''block : bstart sections bend'''
        p[0] = p[2]
        self.pop_block()

    def p_block_arg(self, p):
        '''block : bstart blockargs sections bend'''
        cmds = p[2]
        p[0] = p[3]
        for c in reversed(cmds):
            if not c:
                continue
            p[0] = self.cmd_helper(c, p[0], lineno=p.lineno(2))

        self.pop_block()

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
            p[0] = p[0] + '\n'

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
        p[0] = self.cmd_helper([cmd[1:]],
                               p[2],
                               lineno=p.lineno(1),
                               inline=True)

    def p_inlineblock_cmd_args(self, p):
        """inlineblock : CMD BRACEL vtext sections BRACER"""
        cmd = p[3]
        cmd.insert(0, p[1][1:])
        p[0] = self.cmd_helper(cmd, p[4], lineno=p.lineno(1), inline=True)

    def p_inlineblock_eqn(self, p):
        '''inlineblock : INLINEEQ'''
        p[0] = self.cmd_helper(["math", "inline"], p[1], lineno=p.lineno(1))

    def check_anchor(self, anchor, lineno=-1):
        # internal anchor
        v = self.config['ANCHOR:%s' % anchor]
        if not v:
            v = anchor
            # do not find the anchor, wait for the 2nd scan
            if not self.config.request_scan():
                self._warning("broken anchor '%s'" % v, lineno=lineno)

        return v

    def p_inlineblock_link_withname(self, p):
        '''inlineblock : BRACKETL sections TCELL sections BRACKETR'''
        s = p[2].strip()
        if s[0] == "#":
            s = self.check_anchor(s[1:], lineno=p.lineno(2))
        p[0] = BFunction().tag(p[4], 'a', 'href="%s"' % p[2])

    def p_inlineblock_link(self, p):
        '''inlineblock : BRACKETL sections BRACKETR'''
        s = p[2].strip()
        v = s
        if s[0] == '#':
            # internal anchor
            v = self.check_anchor(s[1:], lineno=p.lineno(2))
        p[0] = BFunction().tag(v, 'a', 'href="%s"' % s)

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
        blk = self.top_block()
        if blk:
            self._error('unmatched block "%s"' % (blk['block']), lineno=blk['lineno'])
        else:
            self._error('syntax %s' % (str(p)), lineno=p.lineno)

    def cmd_helper(self, cmds, data, default='', lineno=-1, inline=False):
        kwargs = self._scan_info(lineno=lineno, inline=inline)
        fun = BFunction.get(cmds[0])
        if not fun:
            # search global function bsmdoc_* to be compatible with previous
            # version
            ldict = lex.get_caller_module_dict(1)
            fun = ldict.get('bsmdoc_' + cmds[0], None)
            if fun:
                self._warning('use decorator @BFunction to define function "%s"' %
                              (cmds[0]), lineno=lineno)
        if fun and hasattr(fun, "__call__"):
            return fun(data, *cmds[1:], **kwargs)

        self._warning('undefined function block "%s".' % cmds[0], lineno=lineno)

        if default:
            return default
        return data


class BFunction(object):
    _interfaces = {}
    scan_info = {}

    def __init__(self, cmd=None):
        self.cmd = cmd

    @classmethod
    def get(cls, intf):
        return cls._interfaces.get(intf, None)

    @classmethod
    def get_all(cls):
        return cls._interfaces

    @classmethod
    def exists(cls, intf):
        return cls._interfaces.get(intf, None)

    def __call__(self, intf):
        name = ""
        if hasattr(intf, '__name__'):
            name = intf.__name__
        if self.cmd:
            name = self.cmd

        if not name:
            raise NameError('Name for function block is missing!')

        if name in BFunction._interfaces and BFunction._interfaces[name].func_closure != intf:
            # if interface(name) is to be overwritten by something different
            _bsmdoc_info('overwrite function block "%s"' % (name), **BFunction.scan_info)

        def wrap(data, *args, **kwargs):
            if hasattr(intf, '__call__'):
                # parse the args from function block, and add it to kwargs
                fun_args, fun_kwargs = _bsmdoc_parse_args(*args)
                kwargs.update({'fun_args': fun_args, 'fun_kwargs': fun_kwargs})
                return str(intf(data, *args, **kwargs))
            elif intf and isinstance(intf, six.string_types):
                # it is defined as an alias (e.g., with \newfun{bsmdoc|CONTENT}),
                # then, \bsmdoc will be replaced with CONTENT
                return intf
            else:
                _bsmdoc_error('unsupported function block "%s"' % (name), **BFunction.scan_info)

            return ''

        wrap.func_closure = intf
        BFunction._interfaces[name] = wrap

        return wrap

    def __getattr__(self, intf):
        if BFunction.exists(intf):
            return BFunction.get(intf)
        raise AttributeError('Undefined interface "%s"' % (intf))


@BFunction('include')
def bsmdoc_include(data, **kwargs):
    filename = data.strip()
    if os.path.isfile(filename):
        return _bsmdoc_readfile(filename, **kwargs)
    else:
        _bsmdoc_error("can't not find %s" % filename, **kwargs)
    return ""


@BFunction('makecontent')
def bsmdoc_makecontent(contents, **kwargs):
    """
    table of contents is a list, each item
    [level, text, label]
        level: 1~6
        text: the caption text
        label: the anchor destination
    """
    if not contents:
        return ""
    first_level = min([c[0] for c in contents])
    call = []
    for c in contents:
        # the text has been parsed, so ignore the parsing here
        txt = BFunction().tag(c[1], 'a', 'href="#%s"' % c[2])
        call.append(['-' * (c[0] - first_level + 1), txt])
    return BFunction().listbullet(call)


@BFunction('escape')
def bsmdoc_escape(data, *args, **kwargs):
    txt = re.sub(r'(<)', r'&lt;', data)
    txt = re.sub(r'(>)', r'&gt;', txt)
    return txt


@BFunction('unescape')
def bsmdoc_unescape(data, *args, **kwargs):
    txt = re.sub(r'(&lt;)', r'<', data)
    txt = re.sub(r'&gt;', r'>', txt)
    return txt


def _bsmdoc_info(msg, **kwargs):
    lineno = kwargs.get('lineno', -1)
    filename = kwargs.get('filename', '') or kwargs.get('include', '')
    silent = kwargs.get('silent', False)
    indent = kwargs.get('indent', 0)
    if silent:
        return
    info = msg
    if lineno != -1:
        info = "%3d: %s" % (lineno, info)
    if filename:
        info = ' '.join([click.format_filename(filename), info])
    if indent:
        info = '    ' * indent + info
    click.echo(info)


def _bsmdoc_error(msg, **kwargs):
    kwargs['silent'] = False
    _bsmdoc_info('Error ' + msg, **kwargs)


def _bsmdoc_warning(msg, **kwargs):
    kwargs['silent'] = False
    _bsmdoc_info('Warning ' + msg, **kwargs)


@BFunction('config')
def bsmdoc_config(data, *args, **kwargs):
    cfg = kwargs['cfg']
    if len(args) <= 0:
        # configuration as text
        _bsmdoc_info("reading configuration ...", **kwargs)
        cfg.load(data)
    elif args[0] == 'bsmdoc_conf':
        _bsmdoc_info('read configuration from file "%s" ...' % data, **kwargs)
        cfg.load(_bsmdoc_readfile(data, **kwargs))
    else:
        if data.lower() in ['true', 'false']:
            data = data.lower() in ['true']
        key = args[0].lower()
        if key in ['label', 'caption']:
            _bsmdoc_warning(
                '\\config{{{0}|}} is depreciated, use \\{0}{{}} instead'.
                format(key), **kwargs)
            key = 'v:' + key
        if len(args) > 1 and args[1].lower().strip() == 'add':
            val = _to_list(cfg[key])
            val += data.split()
            cfg[key] = val
        else:
            cfg[key] = data

    return ""


@BFunction('label')
def bsmdoc_label(data, *args, **kwargs):
    return BFunction().config(data, 'v:label', *args, **kwargs)


@BFunction('caption')
def bsmdoc_caption(data, *args, **kwargs):
    return BFunction().config(data, 'v:caption', *args, **kwargs)


# deal with the equation reference: \ref{} or \eqref{}
@BFunction('eqref')
def bsmdoc_eqref(data, *args, **kwargs):
    return "\\ref{%s}" % data


@BFunction('ref')
def bsmdoc_ref(data, *args, **kwargs):
    # search in links defined with \label{}, so we can use the same
    # syntax to add reference to images, sections, and tables.
    cfg = kwargs.get('cfg')
    v = cfg['ANCHOR:' + data]
    if v:
        return BFunction().tag(v, 'a', 'href="#%s"' % data)
    elif not cfg.request_scan() and not data.startswith('eq'):
        # not find the anchor for the 2nd scan
        _bsmdoc_warning("probably broken anchor '%s'" % data, **kwargs)
    # can not find the anchor, assume its a equation reference for now
    return BFunction().eqref(data, *args, **kwargs)


@BFunction('exec')
def bsmdoc_exec(data, *args, **kwargs):
    cfg = kwargs.get('cfg')
    # check if it only needs to execute the code for the 1st scan
    if args and args[0] == "firstRunOnly" and cfg.get_scan() > 1:
        return ''
    try:
        exec(data, globals())
    except:
        _bsmdoc_error("bsmdoc_exec('%s',%s)" % (data, args), **kwargs)
        traceback.print_exc(file=sys.stdout)
    return ''


@BFunction('newfun')
def bsmdoc_newfun(data, *args, **kwargs):
    if not args or len(args) != 1:
        _bsmdoc_error("invalid function definition (%s, %s)" % (args[0], data),
                      **kwargs)
        return ''
    name = args[0].strip()
    if not name.isidentifier():
        _bsmdoc_error(
            "invalid function name: %s which should only contain letter, number, '-' and '_'"
            % (args[0]), **kwargs)

    BFunction(name)(data)
    return ""


@BFunction('pre')
def bsmdoc_pre(data, *args, **kwargs):
    if args and 'newlineonly' in args:
        # only replace newline with '<br>'
        return "<br>\n".join(data.split("\n"))
    return BFunction().tag(data, "pre")


@BFunction('tag')
def bsmdoc_tag(data, *args, **kwargs):
    if len(args) >= 1:
        tag = args[0].lower().strip()
        if not tag:
            _bsmdoc_warning("empty tag", **kwargs)
            return data
        style = _bsmdoc_style(args[1:])
        tag_start = tag
        tag_end = tag
        data = str(data).strip()
        if style:
            tag_start = tag_start + ' ' + style
        if tag in [
                'div', 'ol', 'ul', 'tr', 'table', 'thead', 'tbody', 'figure'
        ]:
            return "<{0}>\n{1}\n</{2}>\n".format(tag_start, data, tag_end)
        elif tag in ['area', 'base', 'br', 'col', 'embed', 'hr', 'img', \
                'input', 'link', 'meta', 'param', 'source', 'track', 'wbr']:
            return "<{0}>".format(tag_start)
        return "<{0}>{1}</{2}>".format(tag_start, data, tag_end)
    return data


def _code_format(code, obeytabs=False, gobble=0, autogobble=False):
    # replace tab with 4 space
    if not obeytabs:
        code = code.replace('\t', ' ' * 4)
    code = code.split('\n')
    # remove leading/tailing empty lines
    while code and not code[0].strip():
        code.pop(0)
    while code and not code[-1].strip():
        code.pop()

    if not code:
        return ''

    # remove leading space of each line
    if autogobble:
        gobble = len(code[0]) - len(code[0].lstrip())
        for c in code:
            if gobble > len(c) - len(c.lstrip()) and c.strip():
                gobble = 0
                break
    return '\n'.join([c[gobble:].rstrip() for c in code])


@BFunction('math')
def bsmdoc_math(data, *args, **kwargs):
    cfg = kwargs.get('cfg')
    cfg['has_math'] = True
    eqn = BFunction().escape(data)
    if args and args[0] == 'inline':
        return '\\({0}\\)'.format(eqn)

    return BFunction().div('$$\n{0}\n$$'.format(_code_format(eqn, autogobble=True)),
                           'mathjax')


@BFunction('div')
def bsmdoc_div(data, *args, **kwargs):
    data = data.strip()
    if not args:
        _bsmdoc_warning('div block requires at least one argument', **kwargs)
        return data
    return BFunction().tag(data, 'div', *args, **kwargs)


def _to_list(val) -> list:
    if isinstance(val, (list, tuple)):
        return list(val)
    return [val]


def _to_literal(value):
    try:
        return literal_eval(value.strip())
    except:
        # do not strip(), otherwise the space in data will be gone, e.g.,
        # self['image_numbering_prefix'] = 'Fig. '
        return value


def _bsmdoc_parse_args(*args):
    # convert string args
    # for any arg in args, if '=' is in arg, i.e., 'key=value', and key is a
    # valid python identifier, it will be convert to {'key': 'value'}
    # otherwise arg is untouched

    opts = []
    kwargs = {}
    for arg in args:
        arg = arg.strip()
        if '=' in arg:
            tmp = arg.split('=')
            key = tmp[0].strip()
            if key.isidentifier():
                kwargs[key] = _to_literal(''.join(tmp[1:]).strip())
                continue
        opts.append(_to_literal(arg))

    return opts, kwargs


@BFunction('alias')
def bsmdoc_alias(data, *args, **kwargs):
    # define alias: \alias{title|this is the title}
    # use alias: \alias{title}
    cfg = kwargs.get('cfg')
    if not args:
        name = data.strip()
        if name in cfg.alias:
            return cfg.alias[name]
        _bsmdoc_error('undefined alias "%s"' % (name), **kwargs)
    else:
        cfg.alias[args[0].strip()] = data
    return ""


@BFunction('highlight')
def bsmdoc_highlight(code, *args, **kwargs):
    args, opts = kwargs['fun_args'], kwargs['fun_kwargs']
    # format code
    obeytabs = 'obeytabs' in args
    gobble = opts.get('gobble', 0)
    autogobble = 'autogobble' in args
    code = _code_format(code,
                        obeytabs=obeytabs,
                        gobble=gobble,
                        autogobble=autogobble)

    lexer = get_lexer_by_name(args[0], stripnl=False, tabsize=4)
    for key in ['obeytabs', 'gobble', 'autogobble']:
        opts.pop(key, None)
    if "cssclass" not in opts:
        opts['cssclass'] = 'syntax-inline' if kwargs.get('inline', False) else 'syntax'
    # forward all the other args to HtmlFormatter
    formatter = HtmlFormatter(**opts)
    # pygments will replace '&' with '&amp;', which will make the unicode
    # (e.g., &#xNNNN) shown incorrectly.
    txt = highlight(BFunction().unescape(code), lexer, formatter)
    txt = txt.replace('&amp;#x', '&#x')
    txt = txt.replace('&amp;lt;', '&lt;')
    return txt.replace('&amp;gt', '&gt;')


@BFunction('cite')
def bsmdoc_cite(data, *args, **kwargs):
    cfg = kwargs.get('cfg')
    hide = args and args[0] == 'hide'
    ref = cfg.refs.get(data, '')
    ref_tag = 1  # the index of the reference
    cite_tag = 1  # the index of citation of the reference
    if not ref:
        if not cfg.request_scan():
            _bsmdoc_error("can't find the reference: %s" % data, **kwargs)
        return ""
    i = 0
    for i, c in enumerate(cfg.cited):
        if data == c[2]:
            if hide:
                # the reference has already be cited, no need to do anything
                return ""
            c[3] += 1
            cite_tag = c[3]
            ref_tag = c[1]
            break
    else:
        ref_tag = len(cfg.cited) + 1
        cite_tag = 1
        if hide:
            cite_tag = 0
        cfg.cited.append(['', ref_tag, data, cite_tag])
        i = -1
    #
    cite_id_prefix = 'cite-%d-' % (ref_tag)
    ref_id = 'reference-%d' % ref_tag
    # add the reference to the list, which will show at the end of the page
    cite_all = []
    for c in six.moves.range(1, cite_tag + 1):
        anchor = 'href="#%s%d"' % (cite_id_prefix, c)
        cite_all.append(BFunction().tag('&#8617;', 'a', anchor))
    fn = BFunction().tag(ref + ' ' + ' '.join(cite_all), 'div', 'id="%s"' % ref_id)
    cfg.cited[i][0] = fn
    ach = ""
    if not hide:
        cite_id = 'id="%s%d"' % (cite_id_prefix, cite_tag)
        ach = BFunction().tag(ref_tag, 'a', cite_id, 'href="#%s"' % ref_id)
        ach = '[{0}]'.format(ach)
    return ach


@BFunction('reference')
def bsmdoc_reference(data, *args, **kwargs):
    cfg = kwargs['cfg']
    if not args:
        _bsmdoc_error("invalid reference definition: missing alias", **kwargs)
    else:
        k = args[0].strip()
        cfg.refs[k] = data
    return ""


@BFunction('footnote')
def bsmdoc_footnote(data, *args, **kwargs):
    cfg = kwargs['cfg']
    tag = len(cfg.footnotes) + 1
    # the footnote definition id
    src = 'footnote_src-%d' % tag
    # the footnote id
    dec = 'footnote-%d' % tag
    # add the footnote to the list, which will show at the end of the page
    data = data + ' ' + BFunction().tag('&#8617;', 'a', 'href="#%s"' % (src))
    fn = BFunction().div(data, 'id="%s"' % dec)
    cfg.footnotes.append(fn)
    tag = BFunction().tag(tag, 'sup')
    return BFunction().tag(tag, 'a', 'name="%s"' % src, 'href="#%s"' % dec)


@BFunction('heading')
def bsmdoc_heading(data, *args, **kwargs):
    cfg = kwargs['cfg']
    txt = data
    pre = data
    label = cfg['v:label']
    level = len(args[0].strip())
    if cfg['heading_numbering']:
        start = cfg['heading_numbering_start']
        if level >= start:
            # build the header number, e.g., 1.1.1.
            # cfg.heading_tag stores the current tag for each level
            head_tag = cfg.heading_tag
            # build the prefix from parent headers
            pre = ''
            for i in range(start, level):
                pre = pre + str(head_tag.get(i, 1)) + '.'
            # increase the tag for current level
            head_tag[level] = head_tag.get(level, 0) + 1
            pre = pre + str(head_tag[level])

            # reset all the children level, e.g., if the previous level is
            # 1.1.1., and current level is 1.2, then reset the current num
            # for level 3 (===) to 0
            for key in six.iterkeys(head_tag):
                if key > level:
                    head_tag[key] = 0
            # generate the label (e.g., sec-1-1-1) if necessary
            if not label:
                label = 'sec-' + pre.replace('.', '-')
            # add the prefix to the heading text
            txt = pre + ' ' + txt
    # build the contents
    if cfg['heading_in_contents']:
        cfg.contents.append([level, txt, label])
    if label:
        cfg['ANCHOR:%s' % label] = pre
        label = 'id="%s"' % label
    return BFunction().tag(txt, 'h%d' % level, label) + '\n'


def _bsmdoc_next_tag(sec, **kwargs):
    cfg = kwargs['cfg']
    if cfg[sec + '_numbering']:
        cfg[sec + '_numbering_next_tag'] += 1
        prefix = cfg[sec + '_numbering_prefix']
        num = cfg[sec + '_numbering_num_prefix'] + str(cfg[sec + '_numbering_next_tag'])
        return (str(prefix) + num + '.', num)
    return ("", "")


def _bsmdoc_style(args, default_class=None):
    style = []
    style_class = []
    for a in args:
        a = a.strip()
        if not a:
            continue
        # by default, 'class="myclass"' can be written as 'myclass' since it is
        # frequently set. And if an attribute does not contain "=" should be
        # enclosed with quotes, e.g., "controls".
        if '=' not in a:
            if a[0] == '"' and a[-1] == '"':
                if a[1:-1]:
                    style.append(a[1:-1])
            else:
                style_class.append(a)
        else:
            style.append(a)
    if not style_class and default_class:
        style_class.append(default_class)
    if style_class:
        style.append('class="%s"' % (' '.join(style_class)))
    return ' '.join(style)


def _bsmdoc_prepare_numbering(sec, label, **kwargs):
    cfg = kwargs.get('cfg')
    tag, num = _bsmdoc_next_tag(sec, **kwargs)
    if label:
        if cfg.get_scan() == 1 and cfg['ANCHOR%s:' % label]:
            _bsmdoc_warning('duplicated label "%s".' % (label), **kwargs)
        if not num:
            fmt = '{sec} numbering is off, to turn it on: \\config{{{sec}_numbering|True}}'
            _bsmdoc_warning(fmt.format(sec=sec), **kwargs)

        cfg['ANCHOR:%s' % label] = num
        label = 'id="%s"' % label
    if tag:
        tag = BFunction().tag(tag, 'span', 'tag')
    return tag, label


@BFunction('image')
def bsmdoc_image(data, *args, **kwargs):
    data = data.strip()
    cfg = kwargs.get('cfg')
    inline = kwargs.get('inline', False)
    txt = BFunction().tag('', 'img', 'src="%s"' % data, 'alt="%s"' % data, *args)
    if inline:
        return txt
    caption = cfg['v:caption']
    label = cfg['v:label']

    tag, label = _bsmdoc_prepare_numbering('image', label, **kwargs)
    if caption:
        caption = BFunction().tag(tag + ' ' + caption, 'figcaption', "caption")
        txt = '\n'.join([txt, caption])
    return BFunction().tag(txt, 'figure', label, 'figure')


@BFunction('video')
def bsmdoc_video(data, *args, **kwargs):
    cfg = kwargs['cfg']
    src = BFunction().tag("", 'source', 'src="%s"' % data)
    src += "\nYour browser does not support the video tag."
    txt = BFunction().tag(src, 'video', '"controls"')
    caption = cfg['v:caption']
    label = cfg['v:label']
    # if cfg['video_numbering'], use the same numbering as image
    sec = 'image' if cfg['video_numbering'] == 'image' else 'video'

    tag, label = _bsmdoc_prepare_numbering(sec, label, **kwargs)
    if caption:
        caption = BFunction().tag(tag + ' ' + caption, 'div', 'caption')
        txt = '\n'.join([txt, caption])
    return BFunction().tag(txt, 'div', label, 'video')


@BFunction('table')
def bsmdoc_table(data, *args, **kwargs):
    cfg = kwargs['cfg']
    head = ""
    if args:
        head = BFunction().tag(args[0], 'thead')
    body = ""
    if data:
        body = BFunction().tag(data, 'tbody')

    label = cfg['v:label']
    caption = cfg['v:caption']
    tag, label = _bsmdoc_prepare_numbering('table', label, **kwargs)
    if caption:
        caption = BFunction().tag(tag + ' ' + caption, 'caption')
    tbl = BFunction().tag((caption + '\n ' + head + body).strip(), 'table', label)
    return tbl


@BFunction('listbullet')
def bsmdoc_listbullet(data, *args, **kwargs):
    # data is a list, for each item
    # [tag, txt]
    # where tag is [-*]+ (e.g., '---', '-*')
    def listbullet(stack):
        # stack is a list of
        # [index in the parent, parent tag, tag, text]
        c = '\n'.join([BFunction().tag(item[3], "li") for item in stack])
        # only take care of the current level, i.e., leave the parent level to
        # parent
        level = stack[0][2][len(stack[0][1]):]
        for j in level:
            tag = 'ul'
            if j == r'*':
                tag = 'ol'
            c = BFunction().tag(c, tag)
        return c

    if not data:
        return ""
    # add an empty item for guard
    data.append(['', ''])
    html = ""

    tagp_p = ""  # the current parent tag
    idxp = 0  # the index of the last item relative to its parent
    tagp = ""  # the tag of last item

    # hold all the items with the current level
    # [index in the parent, parent tag, tag, text]
    stack = []
    # next item
    i = 0
    while i < len(data):
        tag, txt = data[i]
        if not stack or tag == tagp:
            # same level as the current one, add to the list
            idxp += 1
            stack.append([idxp, tagp_p, tag, txt])
            tagp = tag
            i += 1  # retrieve next item
        elif os.path.commonprefix([tagp, tag]) == tagp:
            # d is the child item of the last item, e.g.,
            # tagp = '--', and tag = '--*'
            # then, tagp ('--') becomes the current parent level
            idxp, tagp_p, tagp = 1, tagp, tag
            stack.append([idxp, tagp_p, tag, txt])
            i += 1
        else:
            # not the prefix of the current level, which means the previous
            # listbullet ends; and start the new one
            # the last idx items are from the same level, build the list
            list_txt = listbullet(stack[-idxp:])
            stack = stack[:-idxp]
            if stack:
                idxp, tagp_p, tagp = stack[-1][0], stack[-1][1], stack[-1][2]
                stack[-1][3] += list_txt
            else:
                # the list does not start with the highest level, e.g.
                # -- level 2 item 1
                # -- level 2 item 2
                # - level 1
                html += list_txt
                idxp, tagp_p, tagp = 0, "", ""
                if i < len(data) - 1:
                    # no warning for the guard item
                    _bsmdoc_warning("potential wrong level in the list",
                                    **kwargs)
    data.pop()  # remove the guard
    return html


@BFunction('anchor')
def bsmdoc_anchor(data, *args, **kwargs):
    data = data.strip()
    cfg = kwargs.get('cfg')
    cfg['ANCHOR:%s' % data] = data
    return BFunction().tag(BFunction().tag("&#x2693;", 'sup'), 'a', 'name="%s"' % data)


def _bsmdoc_readfile(filename, encoding=None, **kwargs):
    if not encoding:
        # encoding is not define, try to detect it
        with open(filename.strip(), 'rb') as fp:
            raw = fp.read()
            encoding = chardet.detect(raw)['encoding']

    _bsmdoc_info("open \"%s\" with encoding \"%s\"" % (filename, encoding),
                 **kwargs)
    with open(filename, 'r', encoding=encoding) as fp:
        txt = fp.read()
        txt = txt.encode('unicode_escape').decode()
        regexp = re.compile(r'\\u([a-zA-Z0-9]{4})', re.M + re.S)
        txt = regexp.sub(r'&#x\1;', txt)
        txt = txt.encode().decode('unicode_escape')
        return txt
    return ""


# generate the html
bsmdoc_conf = """
[html]
begin = <!DOCTYPE html>
    <html>
end= </html>

[header]
begin = <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
end = </head>
content =
bsmdoc_css = ['css/bsmdoc.css']
bsmdoc_js = ['js/bsmdoc.js']
menu_css = ['css/menu.css']
menu_js = ['js/menu.js']
mathjax = <script>
            MathJax = {
                tex: {
                    inlineMath: [['\\\\(', '\\\\)']],
                    tags: "all"
                }
            };
         </script>
         <script id="MathJax-script" async
            src="https://cdn.jsdelivr.net/npm/mathjax@3.0.0/es5/tex-mml-chtml.js">
         </script>
jquery = <script src="https://code.jquery.com/jquery-3.5.1.min.js"
                 integrity="sha256-9/aliU8dGd2tb6OSsuzixeV4y/faTqgFtohetphbbj0="
                 crossorigin="anonymous"></script>

[body]
begin = <body class="nomathjax">
        <div class="layout">
end = </div>
      </body>
# default content is
# %(article_menu)s
# <div class="main">
#     %(article_title)s
#     %(article_content)s
# </div>
content =

[footer]
begin = <div class="footer">
end = </div>
content = <div class="footer-text"> Last updated %(UPDATED)s by
          <a href="http://bsmdoc.feiyilin.com/">bsmdoc</a>%(SOURCE)s.</div>
"""


class BDoc(object):
    """class to generate the html file"""
    def __init__(self, lex_only=False, verbose=False):
        self.verbose = verbose
        self.lex_only = lex_only
        self.parser = BParse(verbose=self.verbose)
        self.cfg = None
        self.output_filename = ""
        self.html = ""
        self.html_text = ""
        self.html_body = ""

    def parse_string(self, text):
        return self.parser.run(text, lex_only=self.lex_only)

    def parse(self, filename, encoding=None):
        txt = _bsmdoc_readfile(filename, encoding, silent=not self.verbose)
        return self.parser.run(txt, filename, self.lex_only)

    def gen(self, filename, encoding=None, output=True):
        html_body = self.parse(filename, encoding)
        if html_body is None:
            return ""

        self.html_body = html_body
        cfg = self.parser.config

        html = []
        html.append(cfg['html:begin'])
        # header
        html.append(cfg['header:begin'])
        html.append('<meta name="generator" content="bsmdoc %s">' % (__version__))
        if cfg['header:content']:
            html.append(cfg['header:content'])

        css = _to_list(cfg['header:bsmdoc_css'])
        js = []
        # include bsmdoc.js to show popup reference window if necessary
        jqueryjs = False
        refjs = False
        if cfg.config.has_section('ANCHOR'):
            refs = ('mjx-eqn-', 'img-', 'video-', 'tbl-', 'footnote-', 'reference-')
            for key in cfg.config.options('ANCHOR'):
                if key.startswith(refs):
                    refjs = jqueryjs = True
                    break

        if refjs:
            js += _to_list(cfg['header:bsmdoc_js'])

        if self.parser.config['show_table_of_contents']:
            # menu.css shall be after bsmdoc.css as it will change the layout
            css += _to_list(cfg['header:menu_css'])
            js += _to_list(cfg['header:menu_js'])
            jqueryjs = True
        css += _to_list(cfg['css'])
        js += _to_list(cfg['js'])
        for c in css:
            if not isinstance(c, str) or not c:
                continue
            html.append(
                BFunction().tag('', 'link', 'rel="stylesheet"', 'href="%s"' % c,
                                'type="text/css"'))
        if cfg['has_math']:
            html.append(cfg['header:mathjax'])
        if jqueryjs and cfg['header:jquery']:
            html.append(cfg['header:jquery'])
        for j in js:
            if not isinstance(j, str) or not j:
                continue
            html.append(
                BFunction().tag('', 'script', 'type="text/javascript"',
                                'language="javascript"', 'src="%s"' % j))
        if cfg['title']:
            html.append(BFunction().tag(cfg['title'], 'title'))
        html.append(cfg['header:end'])

        # body
        html.append(cfg['body:begin'])

        # the body:content defines the main architecture of the body
        article = []
        contents = ''
        if self.parser.config['show_table_of_contents']:
            contents = self.parser.contents
            if contents:
                contents = BFunction().div("\n%s\n" % (contents.replace('%', '%%')), 'menu')

        cfg['body:article_menu'] = contents
        title = self.parser.config['doctitle']
        subtitle = self.parser.config['subtitle']
        if title:
            if subtitle:
                title = title + BFunction().div(subtitle, 'subtitle')
            title = BFunction().div(title, 'toptitle').strip()
            article.append(title)
        cfg['body:article_title'] = title
        article.append(BFunction().div(html_body, 'content'))
        cfg['body:article_content'] = html_body.replace('%', '%%').strip()
        html_body = contents + BFunction().div('\n'.join(article), 'main').strip()
        try:
            if cfg['body:content']:
                html_body = cfg['body:content']
        except:
            traceback.print_exc(file=sys.stdout)

        html.append(html_body)

        # reference
        if cfg.cited:
            cites = [BFunction().tag(x[0], 'li') for x in cfg.cited]
            cites = BFunction().tag('\n'.join(cites), 'ol')
            cites = BFunction().tag(cites, 'div', 'reference')
            html.append(cites)

        html.append(cfg['footer:begin'])
        if cfg.footnotes:
            foots = [BFunction().tag(x, 'li') for x in cfg.footnotes]
            foots = BFunction().tag('\n'.join(foots), 'ol')
            foots = BFunction().tag(foots, 'div', 'footnote')
            html.append(foots)

        cfg["source"] = ''
        if cfg['show_source']:
            cfg["source"] = ' ' + BFunction().tag('(source)', 'a', 'href="%s"' % filename)
        html.append(cfg['footer:content'])
        html.append(cfg['footer:end'])

        html.append(cfg['body:end'])

        html.append(cfg['html:end'])

        self.cfg = cfg
        self.html = html
        self.html_text = '\n'.join(html)
        self.output_filename = os.path.splitext(filename)[0] + '.html'
        if output:
            with open(self.output_filename, 'w', encoding=encoding) as fp:
                fp.write(self.html_text)
        return self.html_text


@click.command()
@click.option('--new-project', '-n', type=click.Path(),
              help="Create a new project from template and exit.")
@click.option('--update-project', '-u', type=click.Path(),
              help="Update project (css, js) and exit.")
@click.option('--new-doc', '-d', type=click.Path(), help="Create a new doc from template and exit.")
@click.option('--lex-only', '-l', is_flag=True, help="Show lexer output and exit.")
@click.option('--yacc-only', '-y', is_flag=True, help="Show the yacc output and exit.")
@click.option('--encoding', '-e', help="Set the input file encoding, e.g. 'utf-8'.")
@click.option('--print-html', '-p', is_flag=True, help="Print the output html without saving to file.")
@click.option('--verbose', '-v', is_flag=True, help="Show more logging.")
@click.version_option(__version__)
@click.argument('files', nargs=-1, type=click.Path(exists=True))
def cli(new_project, update_project, new_doc, files, lex_only, encoding,
        yacc_only, print_html, verbose):
    if new_project:
        new_prj(new_project, verbose)
        return
    elif update_project:
        update_prj(update_project, verbose)
        return
    elif new_doc:
        create_doc(new_doc, verbose)
        return

    for filename in files:
        cur_path = os.getcwd()
        try:
            path, filename = os.path.split(filename)
            if path:
                os.chdir(path)
            bsmdoc = BDoc(lex_only, verbose)
            if yacc_only:
                click.echo(bsmdoc.parse(filename, encoding))
                click.echo('\n')
            else:
                text = bsmdoc.gen(filename, encoding, not print_html)
                if print_html:
                    click.echo(text)
                    click.echo('\n')
        except:
            traceback.print_exc(file=sys.stdout)
        os.chdir(cur_path)

def new_prj(path, verbose):
    try:
        os.mkdir(path)
    except FileExistsError:
        _bsmdoc_error("folder %s exists, choose another name!" % (path))
        return
    import logging
    logging.basicConfig(level=logging.INFO)
    from distutils.dir_util import copy_tree
    from distutils import log
    log.set_verbosity(log.INFO)
    log.set_threshold(log.INFO)
    template = os.path.dirname(os.path.abspath(__file__))
    template = os.path.join(template, 'docs')
    copy_tree(os.path.join(template, 'css'), os.path.join(path, 'css'), verbose=verbose)
    copy_tree(os.path.join(template, 'js'), os.path.join(path, 'js'), verbose=verbose)

    create_doc(os.path.join(path, 'index'), verbose)

def update_prj(path, verbose):
    if not os.path.isdir(path):
        _bsmdoc_error("folder %s doesn't exist, choose another name!" % (path))
        return
    import logging
    logging.basicConfig(level=logging.INFO)
    from distutils.dir_util import copy_tree
    from distutils import log
    log.set_verbosity(log.INFO)
    log.set_threshold(log.INFO)
    template = os.path.dirname(os.path.abspath(__file__))
    template = os.path.join(template, 'docs')
    copy_tree(os.path.join(template, 'css'), os.path.join(path, 'css'), verbose=verbose)
    copy_tree(os.path.join(template, 'js'), os.path.join(path, 'js'), verbose=verbose)

def create_doc(doc, verbose):
    template = os.path.dirname(os.path.abspath(__file__))
    template = os.path.join(template, 'docs/template.bsmdoc')
    text = BFunction().include(template, silent=not verbose)
    if text:
        filename, extension = os.path.splitext(doc)
        if not extension:
            doc = filename + '.bsmdoc'
        if os.path.exists(doc):
            _bsmdoc_error("file %s exists, choose another name!" % (doc))
            return
        import logging
        logging.basicConfig(level=logging.INFO)
        from distutils.file_util import copy_file
        from distutils import log
        log.set_verbosity(log.INFO)
        log.set_threshold(log.INFO)
        copy_file(template, doc, verbose=verbose)

        bsmdoc = BDoc(False, verbose)
        bsmdoc.gen(doc)

if __name__ == '__main__':
    cli()
