//===-- Passes.td - Conversion pass definition file --------*- tablegen -*-===//
//
// Licensed under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//

#ifndef ITERATORS_CONVERSION_PASSES
#define ITERATORS_CONVERSION_PASSES

include "mlir/Pass/PassBase.td"

//===----------------------------------------------------------------------===//
// IteratorsToLLVM
//===----------------------------------------------------------------------===//

def ConvertIteratorsToLLVM : Pass<"convert-iterators-to-llvm", "ModuleOp"> {
  let summary = "Convert the operations from the iterators dialect into the "
                "LLVM dialect";
  let constructor = "mlir::createConvertIteratorsToLLVMPass()";
  let dependentDialects = ["func::FuncDialect", "memref::MemRefDialect"];
}

#endif // ITERATORS_CONVERSION_PASSES
