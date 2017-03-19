import re

from pygments.lexers.html import HtmlLexer, XmlLexer
from pygments.lexers.javascript import JavascriptLexer
from pygments.lexers.css import CssLexer

from pygments.lexer import RegexLexer, DelegatingLexer, include, bygroups, \
    using, this, do_insertions, default, words
from pygments.token import Text, Comment, Operator, Keyword, Name, String, \
    Number, Punctuation, Generic, Other
from pygments.util import get_bool_opt, ClassNotFound
from pygments.lexers.python import PythonLexer

_all__ =['bLexer']
class bLexer(RegexLexer):
    name = 'bsmdoc'
    aliases = ['bsmdoc']
    filenames = ['*.bsmdoc']
    mimetypes = ["text/x-bsmdoc"]
    flags = re.MULTILINE|re.DOTALL

    tokens = {
        'root': [
            include('section'),
            (r'.', Text),
        ],
        'funblock': [
            (r'\{\!', Name.Tag, "#push"),
            (r'\!\}', Name.Tag, "#pop"),
            (r'(exec)(\|\|)(\{\%)', bygroups(Name.Function, Text, Name.Tag), 'pythonblock'),
            (r'(exec)(\|)(firstRunOnly)(\|\|)(\{\%)', bygroups(Name.Function,Text,Name.Tag, Text, Name.Tag), 'pythonblock'),
            (r'((?<=\{\!)[^|\n]*)(\|)', bygroups(Name.Function, Text)),
            (r'((?<=\|\|)[^|\n]*)(\|)', bygroups(Name.Function, Text)),
            (r'([^|\n]*)(\|\|)', bygroups(Name.Tag,Text)),
            (r'([^|\n]*)(\|)', bygroups(Name.Tag,Text)),
            include('section'),
            (r'.', Text),
            ],
        'pythonblock':[
            # highlight with python lexer
            # end
            (r'\%\}', Name.Tag, '#pop'),
            # match every thing except "%}"
            (r'([^\%\}]|(\%(?!\}))|((?<!\%)\}))*(?=\%\})', using(PythonLexer)),
            ],
        'cmdblock':[
            (r'\{', Name.Tag, "#push"),
            (r'\}', Name.Tag, "#pop"),
            (r'([^|\n]*)(\|)', bygroups(Name.Tag,Text)),
            include('section'),
            (r'.', Text),
            ],
        'rawblock': [
            (r'\{\%', Name.Tag, "#push"),
            (r'\%\}', Name.Tag, "#pop"),
            (r'.', Text),
            ],
        'section': [
            # include
            (r'(^\s*\#include)(.*\n)', bygroups(Keyword, Name.Tag)),
            (r'(^\s*\#makecontent)(.*\n)', bygroups(Keyword, Text)),
            # comment
            (r'(?<!\&)\#.*', Comment),
            # section
            (r'^(={1,6})(\s*\{[^\}]*\})', bygroups(Name.Tag, Generic.Heading)),
            (r'^(={1,6})(.+\n)', bygroups(Name.Tag, Generic.Heading)),
            # bullet
            (r'^([\-\*]+)(\s*\{[^\}]*\})', bygroups(Name.Tag, Name.Tag)),
            (r'^([\-\*]+)(.*\n)', bygroups(Name.Tag, Name.Tag)),
            # equation
            (r'\$\$.*\$\$', Name.Tag),
            (r'\$[^\$]*\$', Name.Tag),
            # raw block
            (r'\{\%', Name.Tag, "rawblock"),
            # function block
            #(r'(\{\!)([^|]*||)', bygroups(Name.Tag, Generic.Heading)),
            (r'\{\!', Name.Tag, "funblock"),
            #(r'\{\!|\!\}|\{\%|\%\}|\}\}|\{\{', Name.Tag),
            # command
            #(r'(\\\w+)({)([^|]*|)(.*)(})', bygroups(Name.Tag,Name.Tag,Name.Tag, Text, Name.Tag)),
            (r'(\\\w+)({)', bygroups(Name.Function,Name.Tag), 'cmdblock'),
            (r'(\\\w+)({)(.*)(})', bygroups(Name.Tag,Name.Tag,Text, Name.Tag)),
            # link
            (r'(\[)([^\]\|]+)(\|)([^\]\|]*)(\])', bygroups(Name.Tag, Name.Tag, Text, String, Name.Tag)),
            (r'(\[)([^\]]*)(\])', bygroups(Name.Tag, Name.Tag,Name.Tag)),
            #(r'.*\n', Text),
            ]
    }

    def __init__(self, **options):
        self.handlecodeblocks = get_bool_opt(options, 'handlecodeblocks', True)
        RegexLexer.__init__(self, **options)
