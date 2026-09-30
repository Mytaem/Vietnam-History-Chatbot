// Constraints + indexes (PLAN.md Mục 4). Chạy bởi hgr load.
CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE;
CREATE CONSTRAINT chunk_id  IF NOT EXISTS FOR (c:Chunk)  REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT period_id IF NOT EXISTS FOR (p:Period) REQUIRE p.id IS UNIQUE;
CREATE CONSTRAINT era_id    IF NOT EXISTS FOR (e:Era)    REQUIRE e.id IS UNIQUE;
CREATE CONSTRAINT article_id IF NOT EXISTS FOR (a:Article) REQUIRE a.page_id IS UNIQUE;

CREATE FULLTEXT INDEX entity_names IF NOT EXISTS FOR (e:Entity) ON EACH [e.name, e.aliases_text];
CREATE FULLTEXT INDEX chunk_text   IF NOT EXISTS FOR (c:Chunk)  ON EACH [c.text];
CREATE FULLTEXT INDEX period_names IF NOT EXISTS FOR (p:Period) ON EACH [p.name, p.aliases_text];

CREATE VECTOR INDEX entity_vec IF NOT EXISTS FOR (e:Entity) ON e.embedding
  OPTIONS {indexConfig: {`vector.dimensions`: 1024, `vector.similarity_function`: 'cosine'}};
CREATE VECTOR INDEX chunk_vec IF NOT EXISTS FOR (c:Chunk) ON c.embedding
  OPTIONS {indexConfig: {`vector.dimensions`: 1024, `vector.similarity_function`: 'cosine'}};

CREATE INDEX entity_start IF NOT EXISTS FOR (e:Entity) ON (e.start_year);
CREATE INDEX entity_name  IF NOT EXISTS FOR (e:Entity) ON (e.name);
CREATE INDEX entity_display_name IF NOT EXISTS FOR (e:Entity) ON (e.display_name);
CREATE INDEX chunk_min    IF NOT EXISTS FOR (c:Chunk)  ON (c.min_year);
CREATE INDEX chunk_period IF NOT EXISTS FOR (c:Chunk)  ON (c.period_id);
