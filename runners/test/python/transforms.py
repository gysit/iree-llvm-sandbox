# Bootstrap our local extensions first.
# TODO: Come up with a way to make this auto-load.
import mlir.iree_sandbox

from mlir.ir import *
from mlir.passmanager import *

import mlir.all_passes_registration


class Transform:
  """Base class for all parametrized transformations."""

  def __call__(self, module: Module, func_name: str):
    PassManager.parse(self.pipeline).run(module)


class Fuse(Transform):

  def __init__(self, func_name: str, op_name: str, tile_sizes: list, pad=False):
    pad_str = f'fuse-padding' if pad else ''
    tile_str = f'tile-sizes={",".join([str(ts) for ts in tile_sizes])}'
    pipeline = (
        f'linalg-tensor-codegen-driver{{'
        f'     anchor-func={func_name} '
        f'     anchor-op={op_name} '
        #f'     fuse '
        f'     {pad_str}'
        f'     {tile_str}}},'
        f'canonicalize,'
        f'cse')
    self.pipeline = pipeline


class Tile(Transform):
  """Tile a linalg op with `tile_sizes`.

  This transform can be configured as follows:
  * `tile_sizes`: Tile sizes used for tiling.
  * `pad`: Request padding of tensors.
  * `hoist_padding`: Hoist padding around the specified number of loops. `pad`
     must also be specified.
  * `peel`: Peel the specified loops generated by the tiling pattern. Cannot be
     used together with `pad = True`.
  * `scalarize_dyn_dims`: Scalarize all dimensions that having statically
    unknown size. Either `tile_sizes` or `scalarize_dyn_dims` must be specified.
    Cannot use both at the same time. Cannot be used together with `pad` or
    `peel`.
  """

  def __init__(self,
               func_name: str,
               op_name: str,
               tile_sizes=[],
               pad=False,
               peel=[],
               hoist_padding=None,
               scalarize_dyn_dims=False):
    tile_str = ''
    pad_str = ''
    hoist_padding_str = ''
    peeled_loops_str = ''
    scalarize_dyn_dims_str = ''

    if tile_sizes:
      tile_str = f'tile-sizes={",".join([str(ts) for ts in tile_sizes])}'
    if pad:
      pad_str = 'pad'
    if hoist_padding:
      hoist_padding_str = f'hoist-padding={hoist_padding}'
    if peel:
      loop_indices = [str(l) for l in peel]
      peeled_loops_str = f'peeled-loops={",".join(loop_indices)}'
    if scalarize_dyn_dims:
      scalarize_dyn_dims_str = 'scalarize-dynamic-dims'

    pipeline = (f'linalg-tensor-codegen-driver{{'
                f'     anchor-func={func_name} '
                f'     anchor-op={op_name} '
                f'     {tile_str} '
                f'     {peeled_loops_str} '
                f'     {scalarize_dyn_dims_str} '
                f'     {pad_str} '
                f'     {hoist_padding_str}}},'
                f'canonicalize,'
                f'cse')
    self.pipeline = pipeline


class Vectorize(Transform):

  def __init__(self, func_name: str, op_name: str):
    pipeline = (f'linalg-tensor-codegen-driver{{'
                f'     anchor-func={func_name} '
                f'     anchor-op={op_name} '
                f'     vectorize '
                f'     vectorize-padding}},'
                f'canonicalize,'
                f'cse')
    self.pipeline = pipeline


class Bufferize(Transform):

  def __init__(self):
    pipeline = (f'linalg-tensor-codegen-driver{{'
                f'     bufferize=true}},'
                f'canonicalize,'
                f'cse')
    self.pipeline = pipeline


class LowerVectors(Transform):

  def __init__(self):
    pipeline = (f'linalg-tensor-codegen-driver{{'
                f'    lower-vector '
                f'    split-transfers=vector-transfers '
                f'    vectorize-contraction-to=outerproduct '
                f'    unroll-vector-transfers=true}},'
                f'canonicalize,'
                f'cse')
    self.pipeline = pipeline


class LowerToLLVM(Transform):

  def __init__(self):
    pipeline = (f'linalg-tensor-codegen-driver{{'
                f'    lower-to-llvm}},'
                f'canonicalize,'
                f'cse')
    self.pipeline = pipeline


class Sparsify(Transform):

  def __init__(self, options: str):
    pipeline = (
        f'sparsification{{{options}}},'
        f'sparse-tensor-conversion,'
        f'builtin.func(convert-linalg-to-loops,convert-vector-to-scf),'
        f'convert-scf-to-std,'
        f'func-bufferize,'
        f'tensor-constant-bufferize,'
        f'builtin.func(tensor-bufferize,std-bufferize,finalizing-bufferize),'
        f'convert-vector-to-llvm{{reassociate-fp-reductions=1 enable-index-optimizations=1}},'
        f'lower-affine,'
        f'convert-memref-to-llvm,'
        f'convert-std-to-llvm')
    self.pipeline = pipeline
