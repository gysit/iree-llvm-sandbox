// This test only checks the content of the file parses.
// RUN: mlir-proto-opt %s

pdl.pattern @pdl_target : benefit(1) {
  %args = operands
  %results = types
  %0 = operation "linalg.matmul"(%args : !pdl.range<value>) -> (%results : !pdl.range<type>)
  %1 = pdl.attribute @matmul_tensors
  apply_native_constraint "nestedInFunc"(%0, %1 : !pdl.operation, !pdl.attribute)
  // TODO: we don't want this, but it is the required terminator for pdl.pattern
  rewrite %0 with "iree_linalg_transform.apply"
}

iree_linalg_transform.sequence {
  %0 = match @pdl_target
  vectorize %0 {vectorize_padding = true}
}
