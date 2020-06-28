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

__version__ = '0.0.5'


class BConfig(object):
    """
    class to hold all the configurations
    """
    def __init__(self):
        self.verbose = False
        self.lex = False

        self.config = configparser.SafeConfigParser(delimiters=('=', ))
        self.load(bsmdoc_conf)
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
        self._rescan = False

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

        self.set_updated(time.localtime(time.time()), True)
        self['verbose'] = self.verbose
        self['title'] = ''
        self['show_source'] = False
        self['heading_numbering'] = False
        self['heading_numbering_start'] = 1
        self['heading_in_contents'] = True
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
        self.heading_tag = {}
        self.cited = []

    def set_updated(self, t, forced=False):
        if forced or not self['updated']:
            self['updated'] = time.strftime('%Y-%m-%d %H:%M:%S %Z', t)
        else:
            ct = time.strptime(self['updated'], '%Y-%m-%d %H:%M:%S %Z')
            if ct < t:
                self['updated'] = time.strftime('%Y-%m-%d %H:%M:%S %Z', t)

    def get_scan(self):
        return self._scan

    def next_scan(self):
        self._scan += 1

    def need_rescan(self):
        return self._rescan

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
            if not self.config.has_option(sec, '_type_' + key):
                return val
            types = self.config.get(sec, '_type_' + key)
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
        if self.config.has_option(sec, '_type_' + key):
            types_old = self.config.get(sec, '_type_' + key)
            if types != types_old:
                _bsmdoc_warning("%s:%s change type from %s to %s (%s)" %
                                (sec, key, types_old, types, val))
        self.config.set(sec, '_type_' + key, types)

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

        self.html = ""
        self.config = BConfig()
        self.verbose = verbose
        self.filename = ""
        self._input_stack = []
        self._contents = []

        # function block supports embedded block, remember the current block
        # level to print the error message correspondingly when error occurs.
        self.block_state = []
        self.heading_level = 0

    def top_block(self):
        if self.block_state:
            return self.block_state[-1]
        return None

    def pop_block(self):
        if self.block_state:
            args = self.block_state.pop()
            self.heading_level = args['heading_level']
            self.config.set_vars(args['config'])
            args.pop('config', None)
            args.pop('heading_level', None)
            return args

        _bsmdoc_error('no more blocks')
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

    def _run(self, txt):
        # start next scan
        self.config.next_scan()
        # save the table of contents collected from previous scan or empty for
        # 1st scan
        self._contents = self.config.contents
        self.config.reset_options()
        self.config['filename'] = self.filename
        self.config['basename'] = os.path.basename(self.filename)
        mt = time.gmtime(os.path.getmtime(self.filename))
        self.config.set_updated(mt, True)
        lex.lexer.lineno = 1
        yacc.parse(txt, tracking=True)

    def run(self, filename, encoding, lexonly):
        txt = _bsmdoc_readfile(filename, encoding, silent=not self.verbose)
        self.filename = filename
        if lexonly:
            # output the lexer token for debugging
            lex.input(txt)
            tok = lex.token()
            while tok:
                click.echo(tok)
                tok = lex.token()
            return

        _bsmdoc_info("first pass scan ...", silent=not self.verbose)
        self._run(txt)
        if self.config.need_rescan():
            # 2nd scan to resolve the references
            _bsmdoc_info("second pass scan ...", silent=not self.verbose)
            self._run(txt)

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

    def _error(self, msg, line=-1):
        kwargs = {'filename': self.filename, 'lineno': line}
        _bsmdoc_error(msg, **kwargs)

    # lexer
    def t_error(self, t):
        self._error("illegal character '%s'" % (t.value[0]), t.lexer.lineno)
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
        txt = BFunction().include(filename, silent=not self.verbose, cfg=self.config)
        t.lexer.lineno += t.value.count('\n')
        if txt is not None:
            self.push_input(t, txt)
            self.filename = filename
            if os.path.isfile(filename):
                self.config.set_updated(time.gmtime(os.path.getmtime(filename)), False)
            return t.lexer.token()
        else:
            self._error("can't not find %s" % filename, t.lexer.lineno)
            return None

    def t_MAKECONTENT(self, t):
        r'\#makecontent[^\S\r\n]*$'
        if self._contents:
            content = bsmdoc_makecontent(self._contents)
            self.push_input(t, content)
            self.filename = "CONTENTS"
            return t.lexer.token()

        self.config.request_rescan()
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
        t.value = bsmdoc_escape(t.value)
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

    # default state, ignore, '!}', '%}', '|', '[', ']', '{', '}', '\n', ' ', '#', '$'
    def t_WORD(self, t):
        r'(?:\\(\W)|(\!(?!\}))|(\%(?!\}))|(?<=\&)\#|[^ \$\%\!\#\n\|\{\}\[\]\\])+'
        t.value = bsmdoc_escape(t.value)
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
            p[0] = bsmdoc_tag(p[1].strip(), 'p') + '\n'
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
        row = ''.join([bsmdoc_tag(t.strip(), 'td') for t in p[1]])
        p[0] = bsmdoc_tag(row, 'tr')

    def p_thead(self, p):
        '''thead : vtext THEAD rowsep'''
        # THEAD indicates the current row is header
        tr = ''.join([bsmdoc_tag(t.strip(), 'th') for t in p[1]])
        p[0] = bsmdoc_tag(tr, 'tr')

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

    def p_inlineblock_link_withname(self, p):
        '''inlineblock : BRACKETL sections TCELL sections BRACKETR'''
        p[0] = bsmdoc_tag(p[4], 'a', 'href="%s"' % p[2])

    def p_inlineblock_link(self, p):
        '''inlineblock : BRACKETL sections BRACKETR'''
        s = p[2].strip()
        v = s
        if s[0] == '#':
            # internal anchor
            v = self.config['ANCHOR:%s' % s[1:]]
            if not v:
                v = s[1:]
                # do not find the anchor, wait for the 2nd scan
                if not self.config.request_rescan():
                    kwargs = {'lineno': p.lineno(2), 'filename': self.filename}
                    _bsmdoc_warning("broken anchor '%s'" % v, **kwargs)
        p[0] = bsmdoc_tag(v, 'a', 'href="%s"' % s)

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
            self._error("unmatched block '%s'" % (blk['block']), blk['lineno'])
        else:
            click.echo("error: ", p)

    def cmd_helper(self, cmds, data, default='', lineno=-1, inline=False):
        kwargs = {
            'lineno': lineno,
            'inline': inline,
            'silent': not self.verbose,
            'filename': self.filename,
            'cfg': self.config
        }
        fun = BFunction.get(cmds[0])
        if not fun:
            # search global function bsmdoc_* to be compatible with previous
            # version
            ldict = lex.get_caller_module_dict(1)
            fun = ldict.get('bsmdoc_' + cmds[0], 'none')
            _bsmdoc_warning('Use decorator @BFunction to define function "%s"' % (cmds[0]))
        if fun and hasattr(fun, "__call__"):
            return str(fun(data, *cmds[1:], **kwargs))
        elif fun and len(cmds) == 1 and not data \
             and isinstance(fun, six.string_types):
            # it is defined as an alias (e.g., with \newfun{bsmdoc|CONTENT}),
            # then, \bsmdoc will be replaced with CONTENT
            return fun
        else:
            f = '%s(%s)' % (cmds[0], ",".join(cmds[1:]))
            _bsmdoc_warning('undefined function block "%s".' % (f), **kwargs)
        if default:
            return default
        return data


class BFunction(object):
    _interfaces = {}

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

        BFunction._interfaces[name] = intf
        return intf

    def __getattr__(self, intf):
        if BFunction.exists(intf):
            return BFunction.get(intf)
        raise AttributeError('Undefined interface "%s"' % (intf))


@BFunction('include')
def bsmdoc_include(data, **kwargs):
    filename = data.strip()
    if os.path.isfile(filename):
        return _bsmdoc_readfile(filename, **kwargs)
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
        txt = '[#{0}|{{%{1}%}}]'.format(c[2], c[1])
        call.append('-' * (c[0] - first_level + 1) + txt)
    return '\n'.join(call)


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
    filename = kwargs.get('filename', '')
    silent = kwargs.get('silent', False)
    if silent:
        return
    info = msg
    if lineno != -1:
        info = "%d %s" % (lineno, info)
    if filename:
        info = ' '.join([filename, info])
    click.echo(info)


def _bsmdoc_error(msg, **kwargs):
    kwargs['silent'] = False
    _bsmdoc_info('error: ' + msg, **kwargs)


def _bsmdoc_warning(msg, **kwargs):
    kwargs['silent'] = False
    _bsmdoc_info('warning: ' + msg, **kwargs)


@BFunction('config')
def bsmdoc_config(data, *args, **kwargs):
    cfg = kwargs['cfg']
    if len(args) <= 0:
        # configuration as text
        _bsmdoc_info("reading configuration...", **kwargs)
        cfg.load(data)
    elif args[0] == 'bsmdoc_conf':
        _bsmdoc_info("read configuration from file %s..." % data, **kwargs)
        cfg.load(_bsmdoc_readfile(data, silent=kwargs.get('silent', False)))
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
        key = args[0].lower()
        if key in ['label', 'caption']:
            _bsmdoc_warning(
                '\\config{{{0}|}} is depreciated, use \\{0}{{}} instead'.
                format(key), **kwargs)
            key = 'v:' + key
        if len(args) > 1 and args[1].lower() == 'add':
            cfg[key] = cfg[key] + ' ' + data
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
    elif not cfg.request_rescan() and not data.startswith('eq'):
        # do not find the anchor, wait for the 2nd scan
        _bsmdoc_warning("Probably broken anchor '%s'" % data, **kwargs)
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
    if not re.match("^[A-Za-z0-9_-]*$", args[0]):
        _bsmdoc_error(
            "invalid function name: %s which should only contain letter, number, '-' and '_'"
            % (args[0]), **kwargs)

    BFunction(args[0].strip())(data)
    return ""
    #return bsmdoc_exec('bsmdoc_{0}="{1}"'.format(args[0], data), [], **kwargs)


@BFunction('pre')
def bsmdoc_pre(data, *args, **kwargs):
    if args and 'newlineonly' in args:
        # only replace newline with '<br>'
        return "<br>\n".join(data.split("\n"))
    return BFunction().tag(data, "pre")


@BFunction('tag')
def bsmdoc_tag(data, *args, **kwargs):
    if len(args) >= 1:
        tag = args[0].lower()
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
            if gobble > len(c) - len(c.lstrip()) and len(c.strip()) > 0:
                gobble = 0
                break
    for i in range(len(code)):
        code[i] = code[i][gobble:].rstrip()
    return '\n'.join(code)


@BFunction('math')
def bsmdoc_math(data, *args, **kwargs):
    cfg = kwargs.get('cfg')
    cfg['has_math'] = True
    eqn = BFunction().escape(data)
    if args and args[0] == 'inline':
        return '${0}$'.format(eqn)

    return BFunction().div('$$\n{0}\n$$'.format(_code_format(eqn, autogobble=True)),
                           'mathjax')


@BFunction('div')
def bsmdoc_div(data, *args, **kwargs):
    data = data.strip()
    if not args:
        _bsmdoc_warning('div block requires at least one argument', **kwargs)
        return data
    return BFunction().tag(data, 'div', *args, **kwargs)


def _get_opts(*args):
    opts = dict((n.strip(), v.strip())
                for n, v in (a.split('=') for a in args if '=' in a))
    args = [a for a in args if '=' not in a]
    return args, opts


def _to_int(val, default=0):
    try:
        return int(val)
    except ValueError:
        return default


@BFunction('alias')
def bsmdoc_alias(data, *args, **kwargs):
    cfg = kwargs.get('cfg')
    if len(args) == 0:
        return cfg.alias[data.strip()]
    else:
        cfg.alias[args[0].strip()] = data
    return ""


@BFunction('highlight')
def bsmdoc_highlight(code, *args, **kwargs):
    args, opts = _get_opts(*args)
    # format code
    obeytabs = 'obeytabs' in args
    gobble = _to_int(opts.get('gobble', 0))
    autogobble = 'autogobble' in args
    code = _code_format(code,
                        obeytabs=obeytabs,
                        gobble=gobble,
                        autogobble=autogobble)

    lineno = 'inline' if 'lineno' in args else False
    lexer = get_lexer_by_name(args[0], stripnl=False, tabsize=4)
    formatter = HtmlFormatter(linenos=lineno, cssclass="syntax")
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
        if not cfg.request_rescan():
            _bsmdoc_error("Can't find the reference: %s" % data, **kwargs)
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
        cfg[sec + '_next_tag'] += 1
        prefix = cfg[sec + '_numbering_prefix']
        num = cfg[sec + '_numbering_num_prefix'] + str(cfg[sec + '_next_tag'])
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
    tag = ''
    if label:
        (tag, num) = _bsmdoc_next_tag('image', **kwargs)
        if cfg.get_scan() == 1 and cfg['ANCHOR%s:' % label]:
            _bsmdoc_warning('duplicated label "%s".' % (label), **kwargs)

        cfg['ANCHOR:%s' % label] = num
        label = 'id="%s"' % label
        tag = BFunction().tag(tag, 'span', 'tag')
    if caption:
        caption = BFunction().tag(tag + ' ' + caption, 'figcaption', "caption")
        txt = txt + '\n' + caption
    return BFunction().tag(txt, 'figure', label, 'figure')


@BFunction('video')
def bsmdoc_video(data, *args, **kwargs):
    cfg = kwargs['cfg']
    src = BFunction().tag("", 'source', 'src="%s"' % data)
    src += "\nYour browser does not support the video tag."
    txt = BFunction().tag(src, 'video', '"controls"')
    caption = cfg['v:caption']
    label = cfg['v:label']
    tag = ''
    if label:
        (tag, num) = _bsmdoc_next_tag('image', **kwargs)
        if cfg.get_scan() == 1 and cfg['ANCHOR:' + label]:
            _bsmdoc_warning('duplicated label %s".' % (label), **kwargs)

        cfg['ANCHOR:%s' % label] = num
        label = 'id="%s"' % label
        tag = BFunction().tag(tag, 'span', 'tag')

    if caption:
        caption = BFunction().tag(tag + ' ' + caption, 'div', 'caption')
        txt += '\n' + caption
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
    tag = ''
    # add the in-page link
    if label:
        (tag, num) = _bsmdoc_next_tag('table', **kwargs)
        cfg['ANCHOR:%s' % label] = num
        label = 'id="%s"' % label
        tag = BFunction().tag(tag, 'span', 'tag')
    caption = cfg['v:caption']
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
    return BFunction().tag(BFunction().tag("&#x2693;", 'sup'), 'a', 'name="%s"' % data)


def _bsmdoc_readfile(filename, encoding=None, **kwargs):
    if not encoding:
        try:
            # encoding is not define, try to detect it
            raw = open(filename.strip(), 'rb').read()
            result = chardet.detect(raw)
            encoding = result['encoding']
        except IOError:
            traceback.print_exc(file=sys.stdout)
            return ""
    _bsmdoc_info("open \"%s\" with encoding \"%s\"" % (filename, encoding),
                 **kwargs)
    txt = ""
    fp = io.open(filename, 'r', encoding=encoding)
    txt = fp.read()
    fp.close()
    txt = txt.encode('unicode_escape')
    txt = txt.decode()
    regexp = re.compile(r'\\u([a-zA-Z0-9]{4})', re.M + re.S)
    txt = regexp.sub(r'&#x\1;', txt)
    txt = txt.encode().decode('unicode_escape')
    return txt


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
end = <title>%(TITLE)s</title>
    </head>
content = <link rel="stylesheet" href="css/bsmdoc.css" type="text/css">
mathjs = <script>
    MathJax = {
        tex: {
            inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
            tags: "all"
        }
    };
    </script>

    <script id="MathJax-script" async
        src="https://cdn.jsdelivr.net/npm/mathjax@3.0.0/es5/tex-mml-chtml.js">
    </script>

[body]
begin = <body class="nomathjax">
    <div class="layout">
end = </div>
    </body>

[footer]
begin = <div class="footer">
end = </div>
content = <div class="footer-text"> Last updated %(UPDATED)s by
          <a href="http://bsmdoc.feiyilin.com/">bsmdoc</a> %(SOURCE)s.</div>
"""


class Bdoc(object):
    """class to generate the html file"""
    def __init__(self, lexonly, verbose):
        self.verbose = verbose
        self.lexonly = lexonly
        self.parser = None
        self.cfg = None
        self.output_filename = ""
        self.html = ""
        self.html_text = ""

    def bsmdoc_gen(self, filename, encoding=None, output=True):
        self.parser = BParse(verbose=self.verbose)
        self.parser.run(filename, encoding, self.lexonly)
        if self.lexonly:
            return
        cfg = self.parser.config

        html = []
        html.append(cfg['html:begin'])
        # header
        html.append(cfg['header:begin'])
        html.append('<meta name="generator" content="bsmdoc %s">'%(__version__))
        html.append(cfg['header:content'])
        for c in cfg['css'].split(' '):
            if not c:
                continue
            html.append(
                bsmdoc_tag('', 'link', 'rel="stylesheet"', 'href="%s"' % c,
                           'type="text/css"'))
        if cfg['has_math']:
            html.append(cfg['header:mathjs'])
        for j in cfg['js'].split(' '):
            if not j:
                continue
            html.append(
                bsmdoc_tag('', 'script', 'type="text/javascript"',
                           'language="javascript"', 'src="%s"' % j))
        html.append(cfg['header:end'])
        # body
        html.append(cfg['body:begin'])
        subtitle = cfg['subtitle']
        if subtitle:
            subtitle = bsmdoc_tag(subtitle, 'div', 'subtitle')
        doctitle = cfg['doctitle']
        if doctitle:
            doctitle = bsmdoc_tag(doctitle + subtitle, 'div', 'toptitle')
        html.append(doctitle)
        html.append(self.parser.html)
        # reference
        if cfg.cited:
            cites = [bsmdoc_tag(x[0], 'li') for x in cfg.cited]
            cites = bsmdoc_tag('\n'.join(cites), 'ol')
            cites = bsmdoc_tag(cites, 'div', 'reference')
            html.append(cites)

        html.append(cfg['footer:begin'])
        if cfg.footnotes:
            foots = [bsmdoc_tag(x, 'li') for x in cfg.footnotes]
            foots = bsmdoc_tag('\n'.join(foots), 'ol')
            foots = bsmdoc_tag(foots, 'div', 'footnote')
            html.append(foots)

        cfg["source"] = ''
        if cfg['show_source']:
            cfg["source"] = bsmdoc_tag('(source)', 'a', 'href="%s"' % filename)
        html.append(cfg['footer:content'])
        html.append(cfg['footer:end'])

        html.append(cfg['body:end'])

        html.append(cfg['html:end'])

        self.cfg = cfg
        self.html = html
        self.html_text = '\n'.join(html)
        self.output_filename = os.path.splitext(filename)[0] + '.html'
        if output:
            with open(self.output_filename, 'w') as fp:
                fp.write(self.html_text)


@click.command()
@click.option('--lex-only', is_flag=True, help="Show lexer output and exit.")
@click.option('--encoding', help="Set the input file encoding, e.g. 'utf-8'.")
@click.option('--print-html', is_flag=True, help="Print the output html.")
@click.option('--verbose', is_flag=True)
@click.version_option(__version__)
@click.argument('filename', type=click.Path(exists=True))
def cli(filename, lex_only, encoding, print_html, verbose):
    bsmdoc = Bdoc(lex_only, verbose)
    bsmdoc.bsmdoc_gen(click.format_filename(filename), encoding, not print_html)
    if print_html:
        click.echo(bsmdoc.html_text)


if __name__ == '__main__':
    cli()
