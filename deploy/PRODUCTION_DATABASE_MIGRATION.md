# Production database migration to revision 0036

The deployment script permits one schema transition from
`0020_assessment_records` to `0036_azure_collection_state`. Every other
revision mismatch remains blocked.

Before changing the schema, the script creates a PostgreSQL custom-format
backup with the existing private database container. It validates the archive
with `pg_restore --list`, writes a SHA-256 checksum, and restricts the backup
directory and files to the deployment user. The files are retained at:

```text
~/monitorai-v22/releases/<release-id>/database-backup/
```

The script upgrades with the candidate application image and verifies that the
database reached the candidate Alembic head before replacing the application
container. Application rollback continues to restore only the previous image.
It does not reverse the database migration.

## Recovery reference

Keep the release directory until the migration and authenticated production
checks are complete. Before attempting a restore, stop application writes and
verify the archive checksum from its backup directory:

```bash
sha256sum --check monitorai-before-0036.dump.sha256
```

Restore is a manual operator action. Use the PostgreSQL container and the
credentials already supplied through its environment. Restore into a newly
created recovery database first, validate the recovered data, and change the
production database only under an approved recovery procedure. A representative
archive restore command inside the container is:

```bash
pg_restore --username "$POSTGRES_USER" --dbname "$RECOVERY_DATABASE" \
  --clean --if-exists --no-owner --no-privileges /path/to/monitorai-before-0036.dump
```

Do not add database passwords or decrypted Azure credentials to the release
directory, backup metadata, command history, or deployment logs.
