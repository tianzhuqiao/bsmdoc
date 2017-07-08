if exists("b:current_syntax")
  finish
endif
let b:current_syntax = "bsmdoc"

" keywords
" brace text
syn region bBraceBlock matchgroup=bTag start="\(\\\)\@<!{" end="\(\\\)\@<!}" contains=bBraceBlock,bFunBlock,bRawBlock,bCmdBlock
" section
syn region bSectionBlock matchgroup = bTag start="^\s*=\+" end='$' contains=bBraceBlock,bCmdBlock

" function block
syn match bFunBlockCmdArgs /[^|{!}\[\]]*\ze\s*|/ contained contains=bEscape
syn match bFunBlockCmd /\(||\)\@<=\s*\i*\ze\s*|/ contained
syn match bFunBlockCmd /\({!\)\@<=\s*\i*\ze\s*|/ contained
syn region bFunBlock matchgroup=bTag start='{!' end='!}' contains=bFunBlock,bFunBlockCmdArgs,bFunBlockCmd,bLink,bBulletBlock,bCmdBlock,bRawBlock, bEquation,bComment,bTableBlock
syn region bRawBlock matchgroup=bTag start="{%" end="%}" contains=bRawBlock,bFunBlock,bEquation
syn region bTableBlock matchgroup=bTag start="{{" end="}}" contains=bTableBlock,bFunBlockCmdArgs,bCmdBlock
syn region bEquation matchgroup=bTag start="\$" end="\$"
syn region bLink matchgroup=bTag start='\[\s*' end='\]' contains=bLinkUrl,bLinkTitle
syn match bLinkUrl /\(\[\)\@<=[^|\]]*\ze\s*/ contained
syn match bLinkTitle /\(|\)\@<=[^|\]]*\ze\s*/ contained
syn region bBulletBlock matchgroup=bTag start="^\s*[\-\*]\+" end='$' contains=bCmdBlock,bLink,bBraceBlock,bFunBlock,bRawBlock
syn region bBulletBlock matchgroup=bTag start="^\s*[\-\*]\+\s*{" end='}\|%stopzone\>' contains=bBraceBlock,bFunBlock,bRawBlock,bCmdBlock,bLink
syn match bCmdBlockCmd /\({\)\@<=\s*\i*\ze\s*|/ contained
syn region bCmdBlock matchgroup=bTag start="\\\w\+\s*{" end='\(\\\)\@<!}\|%stopzone\>' contains=bBraceBlock,bCmdBlockCmd
syn match bComment "#.*$"
syn match bEscape "\(\\\)\@<=\S\+"

hi def link bFunBlockCmd Function
hi def link bFunBlockCmdArgs String
hi def link bTag Tag
hi def link bLinkUrl Underlined
hi def link bLinkTitle Statement
hi def link bEquation Tag
hi def link bComment Comment
hi def link bBrace Tag
hi def link bSectionBlock Title
hi def link bBulletBlock Tag
hi def link bCmdBlockCmd Function

let g:sectionLevel = 0
function! BsmdocBlockMatch(lnum)
    let line= getline(a:lnum)
    let pos = match(line,'{!')
    let s = 0
    while pos!= -1
        let pos = match(line,'{!', pos+1)
        let s = s + 1
    endwhile
    let pos = match(line,'!}')
    let e = 0
    while pos!= -1
        let pos = match(line,'!}', pos+1)
        let e = e + 1
    endwhile
    return s-e
endfunction

function! FoldLevel()
    let line=getline(v:lnum)
    " stop section folding in "{!", "!}"
    let g:sectionLevel = g:sectionLevel + BsmdocBlockMatch(v:lnum)
    if g:sectionLevel > 0
        return "="
    endif
    if line =~ '^======'
        return ">6"
    elseif line =~ '^====='
        return ">5"
    elseif line =~ '^===='
        return ">4"
    elseif line =~ '^==='
        return ">3"
    elseif line =~ '^=='
        return ">2"
    elseif line =~ '^='
        return ">1"
    endif
    " check the next line
    let line=getline(v:lnum+1)
     if line =~ '^======'
        return "<6"
    elseif line =~ '^====='
        return "<5"
    elseif line =~ '^===='
        return "<4"
    elseif line =~ '^==='
        return "<3"
    elseif line =~ '^=='
        return "<2"
    elseif line =~ '^='
        return "<1"
    endif
    return "="
endfunction
au BufEnter *.bsmdoc setlocal foldexpr=FoldLevel()
au BufEnter *.bsmdoc setlocal foldmethod=expr

