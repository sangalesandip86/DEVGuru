-- v3.1 Change Set linkage: changeset-schema gains story_refs[], each task gains ac_refs[].
ALTER TABLE change_sets ADD COLUMN story_refs TEXT NOT NULL DEFAULT '[]';
ALTER TABLE tasks ADD COLUMN ac_refs TEXT NOT NULL DEFAULT '[]';
