# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/01_maker.ipynb.

# %% auto 0
__all__ = ['find_var', 'read_var', 'update_var', 'ModuleMaker', 'retr_exports', 'make_code_cell', 'make_code_cells',
           'relative_import', 'update_import', 'basic_export_nb2']

# %% ../nbs/01_maker.ipynb 3
from .read import *
from .imports import *

from fastcore.script import *
from fastcore.imports import *

import ast,contextlib

from collections import defaultdict
from pprint import pformat
from textwrap import TextWrapper

# %% ../nbs/01_maker.ipynb 7
def find_var(lines, varname):
    "Find the line numbers where `varname` is defined in `lines`"
    start = first(i for i,o in enumerate(lines) if o.startswith(varname))
    if start is None: return None,None
    empty = ' ','\t'
    if start==len(lines)-1 or lines[start+1][:1] not in empty: return start,start+1
    end = first(i for i,o in enumerate(lines[start+1:]) if o[:1] not in empty)
    return start,len(lines) if end is None else (end+start+1)

# %% ../nbs/01_maker.ipynb 9
def read_var(code, varname):
    "Eval and return the value of `varname` defined in `code`"
    lines = code.splitlines()
    start,end = find_var(lines, varname)
    if start is None: return None
    res = [lines[start].split('=')[-1].strip()]
    res += lines[start+1:end]
    try: return eval('\n'.join(res))
    except SyntaxError: raise Exception('\n'.join(res)) from None

# %% ../nbs/01_maker.ipynb 11
def update_var(varname, func, fn=None, code=None):
    "Update the definition of `varname` in file `fn`, by calling `func` with the current definition"
    if fn:
        fn = Path(fn)
        code = fn.read_text()
    lines = code.splitlines()
    v = read_var(code, varname)
    res = func(v)
    start,end = find_var(lines, varname)
    del(lines[start:end])
    lines.insert(start, f"{varname} = {res}")
    code = '\n'.join(lines)
    if fn: fn.write_text(code)
    else: return code

# %% ../nbs/01_maker.ipynb 14
class ModuleMaker:
    "Helper class to create exported library from notebook source cells"
    def __init__(self, dest, name, nb_path, is_new=True):
        dest,nb_path = Path(dest),Path(nb_path)
        store_attr()
        self.fname = dest/(name.replace('.','/') + ".py")
        if is_new: dest.mkdir(parents=True, exist_ok=True)
        else: assert self.fname.exists(), f"{self.fname} does not exist"
        self.dest2nb = nb_path.relpath(dest)
        self.hdr = f"# %% {self.dest2nb}"

# %% ../nbs/01_maker.ipynb 17
_def_types = ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef
_assign_types = ast.AnnAssign, ast.Assign, ast.AugAssign

def _val_or_id(it): return [getattr(o, 'value', getattr(o, 'id', None)) for o in it.value.elts]
def _all_targets(a): return L(getattr(a,'elts',a))
def _filt_dec(x): return getattr(x,'id','').startswith('patch')
def _wants(o): return isinstance(o,_def_types) and not any(L(o.decorator_list).filter(_filt_dec))

# %% ../nbs/01_maker.ipynb 18
def retr_exports(trees):
    # include anything mentioned in "_all_", even if otherwise private
    # NB: "_all_" can include strings (names), or symbols, so we look for "id" or "value"
    assigns = trees.filter(risinstance(_assign_types))
    all_assigns = assigns.filter(lambda o: getattr(o.targets[0],'id',None)=='_all_')
    all_vals = all_assigns.map(_val_or_id).concat()
    syms = trees.filter(_wants).attrgot('name')

    # assignment targets (NB: can be multiple, e.g. "a=b=c", and/or destructuring e.g "a,b=(1,2)")
    assign_targs = L(L(assn.targets).map(_all_targets).concat() for assn in assigns).concat()
    exports = (assign_targs.attrgot('id')+syms).filter(lambda o: o and o[0]!='_')
    return (exports+all_vals).unique()

# %% ../nbs/01_maker.ipynb 19
@patch
def make_all(self:ModuleMaker, cells):
    "Create `__all__` with all exports in `cells`"
    if cells is None: return ''
    return retr_exports(cells.map(NbCell.parsed_).concat())

# %% ../nbs/01_maker.ipynb 20
def make_code_cell(code): return AttrDict(source=code, cell_type="code")
def make_code_cells(*ss): return dict2nb({'cells':L(ss).map(make_code_cell)}).cells

# %% ../nbs/01_maker.ipynb 23
def relative_import(name, fname, level=0):
    "Convert a module `name` to a name relative to `fname`"
    assert not level
    sname = name.replace('.','/')
    if not(os.path.commonpath([sname,fname])): return name
    rel = os.path.relpath(sname, fname)
    if rel==".": return "."
    res = rel.replace(f"..{os.path.sep}", ".")
    return "." + res.replace(os.path.sep, ".")

# %% ../nbs/01_maker.ipynb 25
def update_import(source, tree, libname, f=relative_import):
    if not tree: return
    imps = L(tree).filter(risinstance(ast.ImportFrom))
    if not imps: return
    src = source.splitlines(True)
    for imp in imps:
        nmod = f(imp.module, libname, imp.level)
        lin = imp.lineno-1
        sec = src[lin][imp.col_offset:imp.end_col_offset]
        newsec = re.sub(f"(from +){'.'*imp.level}{imp.module}", fr"\1{nmod}", sec)
        src[lin] = src[lin].replace(sec,newsec)
    return src

@patch
def import2relative(cell:NbCell, libname):
    src = update_import(cell.source, cell.parsed_(), libname)
    if src: cell.set_source(src)

# %% ../nbs/01_maker.ipynb 27
@patch
def make(self:ModuleMaker, cells, all_cells=None, lib_name=None):
    "Write module containing `cells` with `__all__` generated from `all_cells`"
    if lib_name is None: lib_name = get_config().lib_name
    if all_cells is None: all_cells = cells
    for cell in all_cells: cell.import2relative(lib_name)
    if not self.is_new: return self._make_exists(cells, all_cells)

    self.fname.parent.mkdir(exist_ok=True, parents=True)
    _all = self.make_all(all_cells)
    trees = cells.map(NbCell.parsed_)
    try: last_future = max(i for i,tree in enumerate(trees) if tree and any(
         isinstance(t,ast.ImportFrom) and t.module=='__future__' for t in tree))+1
    except ValueError: last_future=0
    with self.fname.open('w') as f:
        f.write(f"# AUTOGENERATED! DO NOT EDIT! File to edit: {self.dest2nb}.")
        write_cells(cells[:last_future], self.hdr, f, 0)
        tw = TextWrapper(width=120, initial_indent='', subsequent_indent=' '*11, break_long_words=False)
        all_str = '\n'.join(tw.wrap(str(_all)))
        f.write(f"\n\n# %% auto 0\n__all__ = {all_str}")
        write_cells(cells[last_future:], self.hdr, f, 1)
        f.write('\n')

# %% ../nbs/01_maker.ipynb 31
@patch
def _update_all(self:ModuleMaker, all_cells, alls):
    return pformat(alls + self.make_all(all_cells), width=160)

@patch
def _make_exists(self:ModuleMaker, cells, all_cells=None):
    "`make` for `is_new=False`"
    if all_cells: update_var('__all__', partial(self._update_all, all_cells), fn=self.fname)
    with self.fname.open('a') as f: write_cells(cells, self.hdr, f)

# %% ../nbs/01_maker.ipynb 37
def basic_export_nb2(fname, name, dest=None):
    "A basic exporter to bootstrap nbprocess using `ModuleMaker`"
    if dest is None: dest = get_config().path('lib_path')
    cells = L(c for c in read_nb(fname).cells if re.match(r'#\|\s*export', c.source))
    ModuleMaker(dest=dest, name=name, nb_path=fname).make(cells)
