import os
import sys
import traceback
import logging
import shutil
import click
from click_default_group import DefaultGroup
from .bsmdoc import BDoc, _bsmdoc_error
from .version import __version__

logging.basicConfig(level=logging.INFO)

@click.group(cls=DefaultGroup, default='html', default_if_no_args=True)
@click.version_option(__version__)
def cli():
    pass

@cli.command('html', help='Generate html file.', short_help='Generate html file.')
@click.option('--lex-only', '-l', is_flag=True, help="Show lexer output and exit.")
@click.option('--yacc-only', '-y', is_flag=True, help="Show the yacc output and exit.")
@click.option('--encoding', '-e', help="Set the input file encoding, e.g. 'utf-8'.")
@click.option('--print-html', '-p', is_flag=True,
              help="Print the output html without saving to file.")
@click.option('--verbose', '-v', is_flag=True, help="Show more logging.")
@click.argument('files', nargs=-1, type=click.Path(exists=True, dir_okay=False, allow_dash=True))
def gen_html(files, lex_only, encoding, yacc_only, print_html, verbose):
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


@cli.command('init', help='Initialize a project from template by copying css/js files.',
             short_help='Initialize a project from template by copying css/js files.')
@click.option('--no-index', is_flag=True, help="Do not include index.bsmdoc.")
@click.option('--force', is_flag=True, help="Overwrite if file exits.")
@click.option('--verbose', '-v', is_flag=True, help="Show more logging.")
@click.pass_context
def new_prj(ctx, no_index, force, verbose):
    update_prj('.', force, verbose)
    if not no_index:
        ctx.invoke(new_doc, files=['./index'], force=force, verbose=verbose)


def update_prj(path, force, verbose):
    if not os.path.isdir(path):
        _bsmdoc_error("folder %s doesn't exist, choose another name!" % (path))
        return

    template = os.path.dirname(os.path.abspath(__file__))
    template = os.path.join(template, 'template')
    shutil.copytree(os.path.join(template, 'css'), os.path.join(path, 'css'), dirs_exist_ok=force)
    shutil.copytree(os.path.join(template, 'js'), os.path.join(path, 'js'), dirs_exist_ok=force)



@cli.command('new', help='Create .bsmdoc from template.',
             short_help='Create .bsmdoc from template.')
@click.option('--force', is_flag=True, help="Overwrite if file exits.")
@click.option('--verbose', '-v', is_flag=True, help="Show more logging.")
@click.argument('files', nargs=-1, type=click.Path())
def new_doc(files, force, verbose):
    template = os.path.dirname(os.path.abspath(__file__))
    template = os.path.join(template, 'template/template.bsmdoc')
    for doc in files:
        filename, extension = os.path.splitext(doc)
        if not extension:
            doc = filename + '.bsmdoc'
        if not force and os.path.exists(doc):
            fmt = 'file %s exists, choose another name or overwrite with "--force"!'
            _bsmdoc_error(fmt % (doc))
            return
        shutil.copy(template, doc)

        bsmdoc = BDoc(False, verbose)
        bsmdoc.gen(doc)


@cli.command('update', help='Update the CSS/JS files',
             short_help='Update the CSS/JS files.')
@click.option('--force', is_flag=True, help="Overwrite if file exits.")
@click.option('--verbose', '-v', is_flag=True, help="Show more logging.")
@click.argument('folders', nargs=-1, type=click.Path(exists=True, file_okay=False))
def update_doc(folders, force, verbose):
    for folder in folders:
        update_prj(folder, force=force, verbose=verbose)

if __name__ == '__main__':
    cli()
