# Licensed under the Apache License v2.0 with LLVM Exceptions.
# See https://llvm.org/LICENSE.txt for license information.
# SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception

from dataclasses import dataclass
from typing import Any, List, Union
from xdsl.ir import Block, Region, Operation, SSAValue, ParametrizedAttribute, Data, MLContext, Attribute
from xdsl.dialects.builtin import StringAttr, ArrayAttr, ArrayOfConstraint, IntegerAttr
from xdsl.irdl import AttributeDef, OperandDef, ResultDef, RegionDef, SingleBlockRegionDef, irdl_attr_definition, irdl_op_definition, ParameterDef, AnyAttr, VarOperandDef, builder

# This file contains the relational algebra dialect. This dialect represents
# relational queries in a tree form, simplifying certain optimizations. Apart
# form scalar datatypes, the dialect knows two different kinds of operations:
# expressions that only have expressions in their subtrees and operators that
# can have both operators and expressions in their subtrees.


@irdl_attr_definition
class DataType(ParametrizedAttribute):
  """
  Models a datatype in a relational query.
  """
  name = "rel_alg.datatype"


@irdl_attr_definition
class Int32(DataType):
  """
  Models a int32 type in a relational query.

  Example:

  ```
  !rel_alg.int32
  ```
  """
  name = "rel_alg.int32"


@irdl_attr_definition
class String(DataType):
  """
  Models a string type in a relational query, that can be either nullable or
  not.

  Example:

  ```
  !rel_alg.string<0: !i1>
  ```
  """
  name = "rel_alg.string"

  nullable = ParameterDef(IntegerAttr)

  @staticmethod
  @builder
  def get(val: Union[int, IntegerAttr]) -> 'String':
    if isinstance(val, IntegerAttr):
      return String([val])
    return String([IntegerAttr.from_int_and_width(val, 1)])


class Expression(Operation):
  ...


@irdl_op_definition
class Literal(Expression):
  """
  Defines a literal with value `val` and type `type`.

  Example:

  ```
  rel_alg.literal() ["val" = 5 : !i64, "type" = !rel_alg.int32]
  ```
  """
  name = "rel_alg.literal"

  val = AttributeDef(AnyAttr())
  type = AttributeDef(DataType)

  @builder
  @staticmethod
  def get(val: Attribute, type: DataType) -> 'Literal':
    return Literal.build(attributes={"val": val, "type": type})


@irdl_op_definition
class Column(Expression):
  """
  References a specific column with name `col_name`.

  Example:

  ```
  rel_alg.column() ["col_name" = "a"]
  ```
  """
  name = "rel_alg.column"

  col_name = AttributeDef(StringAttr)

  @builder
  @staticmethod
  def get(col_name: str) -> 'Column':
    return Column.build(attributes={"col_name": StringAttr.from_str(col_name)})


@irdl_op_definition
class Compare(Expression):
  """
  Applies the `comparator` to `left` and `right`.

  Example:

  ```
  rel_alg.compare() ["comparator" = "="] {
    rel_alg.column() ...
  } {
    rel_alg.literal() ...
  }
  ```
  """
  name = "rel_alg.compare"

  comparator = AttributeDef(StringAttr)
  left = SingleBlockRegionDef()
  right = SingleBlockRegionDef()

  @builder
  @staticmethod
  def get(comparator: str, left: Region, right: Region) -> 'Compare':
    return Compare.build(
        attributes={"comparator": StringAttr.from_str(comparator)},
        regions=[left, right])


class Operator(Operation):
  ...


@irdl_op_definition
class Select(Operator):
  """
  Selects all tuples from `table` that fulfill `predicates`.

  Example:

  ```
  rel_alg.select() {
    rel_alg.pandas_table() ...
  } {
    rel_alg.compare() ...
  }
  ```
  """
  name = "rel_alg.select"

  input = SingleBlockRegionDef()
  predicates = SingleBlockRegionDef()

  @staticmethod
  @builder
  def get(input: Region, predicates: Region) -> 'Select':
    return Select.build(regions=[input, predicates])


@irdl_op_definition
class PandasTable(Operator):
  """
  Defines a table with name `table_name` and schema `schema`.

  Example:

  ```
  rel_alg.pandas_table() ["table_name" = "t"] {
    rel_alg.schema_element() ...
    ...
  }
  ```
  """
  name = "rel_alg.pandas_table"

  table_name = AttributeDef(StringAttr)
  schema = SingleBlockRegionDef()

  @staticmethod
  @builder
  def get(name: str, Schema: Region) -> 'PandasTable':
    return PandasTable.build(
        attributes={"table_name": StringAttr.from_str(name)}, regions=[Schema])


@irdl_op_definition
class SchemaElement(Operator):
  """
  Defines a schema element with name `elt_name` and type `elt_type`.

  Example:

  ```
  rel_alg.schema_element() ["elt_name" = "id", "elt_type" = !rel_alg.int32]
  ```
  """
  name = "rel_alg.schema_element"

  elt_name = AttributeDef(StringAttr)
  elt_type = AttributeDef(DataType)

  @staticmethod
  def get(name: str, type: DataType):
    return SchemaElement.build(attributes={
        "elt_name": StringAttr.from_str(name),
        "elt_type": type
    })


@dataclass
class RelationalAlg:
  ctx: MLContext

  def __post_init__(self: 'RelationalAlg'):
    self.ctx.register_attr(DataType)
    self.ctx.register_attr(String)
    self.ctx.register_attr(Int32)

    self.ctx.register_op(PandasTable)
    self.ctx.register_op(SchemaElement)
    self.ctx.register_op(Select)
    self.ctx.register_op(Literal)
    self.ctx.register_op(Column)
    self.ctx.register_op(Compare)
