cd d:\azure-architect-companion
git add backend/app/models/models.py backend/app/services/services.py backend/app/schemas/schemas.py backend/tests/test_relationships_dependencies.py
git commit -m "Fix SQLAlchemy reserved metadata attribute in Relationship model"
git log --oneline -1
