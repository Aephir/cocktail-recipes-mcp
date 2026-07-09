# Example Transcript: Merge Duplicates (Cucumber vs cucumber)

## Dry Run Preview

User:
Merge duplicate ingredients "Cucumber" and "cucumber" into ingredient ID 42, but preview first.

Assistant (MCP tool call):
merge_ingredients(source_ids=[18], target_id=42)

Assistant (result):
{
  "ok": true,
  "data": {
    "preview": {
      "operation": "merge_ingredients",
      "dry_run": true,
      "affected": {
        "source_ids": [18],
        "target_id": 42,
        "count": 1
      }
    },
    "apply_executed": false,
    "result": {
      "would_update_recipe_count": 12,
      "would_remove_ingredient_ids": [18]
    }
  }
}

## Apply

User:
Looks right. Apply the merge.

Assistant (MCP tool call):
merge_ingredients(source_ids=[18], target_id=42, dry_run=false)

Assistant (result):
{
  "ok": true,
  "data": {
    "preview": {
      "operation": "merge_ingredients",
      "dry_run": false,
      "affected": {
        "source_ids": [18],
        "target_id": 42,
        "count": 1
      }
    },
    "apply_executed": true,
    "result": {
      "updated_recipe_count": 12,
      "removed_ingredient_ids": [18],
      "target_id": 42
    }
  }
}
