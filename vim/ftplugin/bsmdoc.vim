" Vim syntax file
" Language: bsmdoc
" Maintainer: Tianzhu Qiao
" Latest Revision: Jul 02 2017

function BGetTopFile()
    " get the top level file. For example, if the current filename is
    " index_content.bsmdoc, it will try to find the index.bsmdoc. If found,
    " it will compile index.bsmdoc; otherwise, compile index_content.bsmdoc
    let filename = split(expand('%:r'), '_')[0].'.bsmdoc'
    if !filereadable(filename)
        " no top level file, return the current one
        let filename = expand('%:p')
    endif
    return filename
endfunction

function BCompile()
    let filename = BGetTopFile()
    execute "silent !bsmdoc.py " . filename
endfunction

function BPreview()
    let filename = BGetTopFile()
    let filename = split(filename, '\.')[0].'.html'
    execute "silent !" . filename
endfunction

" compile
map ll :call BCompile()<CR>
" preview
map lv :call BPreview()<CR>
