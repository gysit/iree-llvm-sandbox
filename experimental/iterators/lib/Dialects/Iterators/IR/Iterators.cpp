//===-- IteratorsDialect.cpp - Iterators dialect ----------------*- C++ -*-===//

#include "iterators/Dialect/Iterators/IR/Iterators.h"

#include "mlir/IR/DialectImplementation.h"
#include "llvm/ADT/TypeSwitch.h"

using namespace mlir;
using namespace mlir::iterators;

//===----------------------------------------------------------------------===//
// Iterators dialect
//===----------------------------------------------------------------------===//

#include "iterators/Dialect/Iterators/IR/IteratorsOpsDialect.cpp.inc"

void IteratorsDialect::initialize() {
#define GET_OP_LIST
  addOperations<
#include "iterators/Dialect/Iterators/IR/IteratorsOps.cpp.inc"
      >();
  addTypes<
#define GET_TYPEDEF_LIST
#include "iterators/Dialect/Iterators/IR/IteratorsOpsTypes.cpp.inc"
      >();
}

//===----------------------------------------------------------------------===//
// Iterators operations
//===----------------------------------------------------------------------===//

#define GET_OP_CLASSES
#include "iterators/Dialect/Iterators/IR/IteratorsOps.cpp.inc"

//===----------------------------------------------------------------------===//
// Iterators types
//===----------------------------------------------------------------------===//

#define GET_TYPEDEF_CLASSES
#include "iterators/Dialect/Iterators/IR/IteratorsOpsTypes.cpp.inc"
