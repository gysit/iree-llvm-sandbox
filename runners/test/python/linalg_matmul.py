import sys, time
from collections.abc import Callable

import numpy as np

from mlir.ir import *
from mlir.dialects import builtin
from mlir.dialects import linalg
from mlir.dialects import std
from mlir.execution_engine import *
from mlir.runtime import *

from harness import *
from experts import *
from compilation import f32

avx512 = True


def gflop_count_matmul(M: int, N: int, K: int):
  return (2.0 * M * N * K) / 1e9


def np_type_to_mlir_type(np_type: np.dtype):
  if np_type == np.float16:
    return F16Type.get()
  elif np_type == np.float32:
    return F32Type.get()
  elif np_type == np.float64:
    return F64Type.get()
  else:
    raise Exception(f'unknown scalar type: {scalar_type}')


def setup_matmul_np(M: int, N: int, K: int, np_type: np.dtype):
  A = np.random.rand(M, K).astype(np_type)
  B = np.random.rand(K, N).astype(np_type)
  C = np.random.rand(M, N).astype(np_type)
  C.fill(0.)
  return [A, B, C]


# The `matmul_main` function entry point connects MLIR compiled files to python
# allocated tensors. This encodes the runtime / compiler contract that:
#   1. The memory corresponding to the `%C : !acc_tensor_t` can be safely
#      written by the compiled code (i.e. linalg.inplaceable = true`).
#   2. The assumed memory layout is the canonical (i, j) order.
# This represents the minimal contract to connect external and compiled code to
# properly test the e2e compilation chain with all batteries included.
#
# For more advanced use cases, including considerations related to parallel
# runtime tasks and special allocators, a runtime abstraction and a more robust
# contract are needed. This is orthogonal to evaluating and benchmarking codegen
# and is the responsibility of projects such as IREE and TFRT.
def matmul_main(entry_point: str,
                fun_to_benchmark: str,
                M: int,
                N: int,
                K: int,
                lhs_type=f32,
                rhs_type=f32,
                acc_type=f32):
  global avx512
  main_fun_attr = 'attributes {llvm.emit_c_interface}'
  if avx512:
    main_fun_attr = f"""attributes {{
        llvm.emit_c_interface,
        passthrough = [["target-cpu", "skylake-avx512"],
                       ["prefer-vector-width", "512"]]}}"""

  return f"""
!lhs_tensor_t = type tensor<{M}x{K}x{str(lhs_type)}>
!rhs_tensor_t = type tensor<{K}x{N}x{str(rhs_type)}>
!acc_tensor_t = type tensor<{M}x{N}x{str(acc_type)}>

// This func declaration is needed for the module to parse in the first place.
// It is subsequently deleted before being constructed
func private @{fun_to_benchmark}(!lhs_tensor_t, !rhs_tensor_t, !acc_tensor_t) -> (!acc_tensor_t)

func @{entry_point}(
      %A : !lhs_tensor_t {{linalg.inplaceable = false,
                           linalg.buffer_layout = affine_map<(i, j)[] -> (i, j)>}},
      %B : !rhs_tensor_t {{linalg.inplaceable = false,
                           linalg.buffer_layout = affine_map<(i, j)[] -> (i, j)>}},
      %C : !acc_tensor_t {{linalg.inplaceable =  true,
                           linalg.buffer_layout = affine_map<(i, j)[] -> (i, j)>}},
      %iters : index) -> !acc_tensor_t
  {main_fun_attr}
{{
  %c0 = constant 0: index
  %c1 = constant 1: index

  %res = scf.for %arg0 = %c0 to %iters step %c1 iter_args(%iterC = %C) -> (!acc_tensor_t) {{
    %r = call @{fun_to_benchmark}(%A, %B, %iterC) :
      (!lhs_tensor_t, !rhs_tensor_t, !acc_tensor_t) -> (!acc_tensor_t)
    scf.yield %r : !acc_tensor_t
  }}

  return %res : !acc_tensor_t
}}
"""


def build_matmul_under_context_manager(entry_point: str, fun_to_benchmark: str,
                                       transform: Callable, M: int, N: int,
                                       K: int, lhs_type, rhs_type, acc_type):
  # Build module and function to benchmark.
  module = Module.parse(
      matmul_main(entry_point, fun_to_benchmark, M, N, K, lhs_type, rhs_type,
                  acc_type))

  # TODO: this erasure is ugly but is currently needed to avoid string stitching
  # If the func declaration is not present the module does not parse.
  # If the func declaration is present and not erased then we fail with
  # `redefinition of symbol`.
  # This situation may be due to internals of `@builtin.FuncOp.from_py_func`
  module.body.operations[0].operation.erase()

  with InsertionPoint(module.body.operations[0]):
    # Actual benchmarked function called under entry_point.
    @builtin.FuncOp.from_py_func(
        RankedTensorType.get((M, K), lhs_type),
        RankedTensorType.get((K, N), rhs_type),
        RankedTensorType.get((M, N), acc_type))
    # TODO: this name must match fun_to_benchmark, make this safer.
    def matmul_on_tensors(lhs, rhs, out):
      # TODO: in the future, should be writeable more concisely as:
      #   zero = std.constant(0.0, elem_type)
      #   tmp = linalg.fill(out, zero)
      #   linalg.matmul(lhs, rhs, tmp)
      zero = std.ConstantOp(
          value=FloatAttr.get(acc_type, 0.), result=acc_type).result
      tensor_zero = linalg.FillOp(output=out, value=zero).results[0]
      return linalg.matmul(lhs, rhs, outs=[tensor_zero])

  func = module.operation.regions[0].blocks[0].operations[0].operation

  global avx512
  attr_list = [
      StringAttr.get('noinline'),
      # ArrayAttr.get([StringAttr.get('alignstack'),
      #                StringAttr.get('4')])
  ]
  if avx512:
    attr_list = attr_list + [
        ArrayAttr.get(
            [StringAttr.get('target-cpu'),
             StringAttr.get('skylake-avx512')]),
        ArrayAttr.get(
            [StringAttr.get('prefer-vector-width'),
             StringAttr.get('512')])
    ]
  func.attributes['passthrough'] = ArrayAttr.get(attr_list)

  layout_map = AffineMap.get(2, 0, [AffineDimExpr.get(0), AffineDimExpr.get(1)])
  input_attr = DictAttr.get({
      'linalg.buffer_layout': AffineMapAttr.get(layout_map),
      'linalg.inplaceable': BoolAttr.get(False)
  })
  output_attr = DictAttr.get({
      'linalg.buffer_layout': AffineMapAttr.get(layout_map),
      'linalg.inplaceable': BoolAttr.get(True)
  })
  func.attributes['arg_attrs'] = ArrayAttr.get(
      [input_attr, input_attr, output_attr])

  # JIT compile.
  start = time.time()
  transformed_module = transform(entry_point, module, fun_to_benchmark)
  execution_engine = ExecutionEngine(transformed_module)
  elapsed_compilation_s = time.time() - start
  print(f'compilation in {elapsed_compilation_s:.{4}}s')

  return module, execution_engine


def compile_and_test_linalg_matmul(M: int,
                                   N: int,
                                   K: int,
                                   ITERS: int,
                                   np_type: np.dtype,
                                   transform: Callable,
                                   dry_run: bool = True):
  entry_point = 'matmul_main'
  fun_to_benchmark = 'matmul_on_tensors'

  # np's A, B and C are hoisted out so they aren't garbage collected.
  A, B, C = setup_matmul_np(M, N, K, np_type)

  def setup_fun():
    # Arguments must be passed as pointers.
    A_memref_ptr, B_memref_ptr, C_memref_ptr = (
        ctypes.pointer(ctypes.pointer(get_ranked_memref_descriptor(t)))
        for t in (A, B, C))
    return A_memref_ptr, B_memref_ptr, C_memref_ptr

  def compile_fun(A_memref_ptr, B_memref_ptr, C_memref_ptr):
    with Context() as ctx, Location.unknown():
      module, execution_engine = build_matmul_under_context_manager(
          entry_point,
          fun_to_benchmark,
          transform,
          M=M,
          N=N,
          K=K,
          lhs_type=np_type_to_mlir_type(np_type),
          rhs_type=np_type_to_mlir_type(np_type),
          acc_type=np_type_to_mlir_type(np_type))
      return module, execution_engine

  def run_fun(A_memref_ptr, B_memref_ptr, C_memref_ptr, **kwargs):
    index_ptr_t = ctypes.c_longlong * 1
    kwargs['execution_engine'].invoke(entry_point, A_memref_ptr, B_memref_ptr,
                                      C_memref_ptr,
                                      index_ptr_t(kwargs['n_iters']))

  # Check results vs NP and print timings.
  # Note that MLIR directly modifies np's tensor memory and the memref_ptr
  # operands are unused here: we can directly look at the result in C.
  def check_fun(A_memref_ptr, B_memref_ptr, C_memref_ptr):
    if not np.allclose(C, np.dot(A, B)):
      delta = C - np.dot(A, B)
      max_abs_delta = max(delta.max(), delta.min(), key=abs)
      raise Exception(f'max_abs_delta: {max_abs_delta} -> FAILURE ')

  setup_and_invoke(
      setup_fun,
      run_fun,
      ITERS,
      gflop_count_matmul(M, N, K),
      compile_fun=compile_fun,
      check_fun=check_fun)


def test_numpy_matmul(M: int, N: int, K: int, ITERS: int, np_type):

  def setup_fun():
    return setup_matmul_np(M, N, K, np_type)

  def run_fun(A, B, C, **kwargs):
    for _ in range(kwargs['n_iters']):
      C.fill(0.)
      np.dot(A, B, out=C)

  setup_and_invoke(setup_fun, run_fun, ITERS, gflop_count_matmul(M, N, K))


def test_torch_matmul(M: int,
                      N: int,
                      K: int,
                      ITERS: int,
                      np_type,
                      num_threads=2):

  def setup_fun():
    import torch
    torch.set_num_threads(num_threads)
    return [torch.from_numpy(t) for t in setup_matmul_np(M, N, K, np_type)]

  def run_fun(A, B, C, **kwargs):
    for _ in range(kwargs['n_iters']):
      C.fill_(0.)
      torch.mm(A, B, out=C)

  setup_and_invoke(setup_fun, run_fun, ITERS, gflop_count_matmul(M, N, K))
