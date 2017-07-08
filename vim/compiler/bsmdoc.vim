if exists('current_compiler')
  finish
endif
let current_compiler = 'bsmdoc'
if exists(":CompilerSet") != 2          " older Vim always used :setlocal
  command -nargs=* CompilerSet setlocal <args>
endif
CompilerSet makeprg=bsmdoc.py
"CompilerSet efm=%C\ %.%#,%A\ \ File\ \"%f\"\\,\ line\ %l%.%#,%Z%[%^\ ]%\\@=%m
"python traceback error
CompilerSet efm=%+GTraceback%.%#
CompilerSet efm+=%E\ \ File\ \"%f\"\\,\ line\ %l%m
CompilerSet efm+=%E\ \ File\ \"%f\"\\,\ line\ %l
CompilerSet efm+=%C%p^
CompilerSet efm+=%+C\ \ \ \ %.%#
CompilerSet efm+=%+C\ \ %.%#
CompilerSet efm+=%Z%[%^\ ]%\\@=%m
"bsmedit error
CompilerSet efm+=%l\ %trror:\ %m
CompilerSet efm+=%l\ %tarning:\ %m
CompilerSet efm+=%tarning:\ %m
CompilerSet efm+=%trror:\ %m
