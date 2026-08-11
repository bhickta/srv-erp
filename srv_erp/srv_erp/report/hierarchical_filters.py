def get_descendant_condition(group_doctype, value_column, parameter):
	"""Return a nested-set condition matching a selected group and all descendants."""
	table = f"`tab{group_doctype}`"
	return (
		f"{value_column} IN ("
		f"SELECT child.name FROM {table} selected "
		f"INNER JOIN {table} child ON child.lft >= selected.lft AND child.rgt <= selected.rgt "
		f"WHERE selected.name = %({parameter})s)"
	)
