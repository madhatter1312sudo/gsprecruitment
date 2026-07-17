"""
Talent OS — Schema migration: seed salary_benchmarks with
Brainport Eindhoven tech market data (EUR, 2024 estimates).
"""

MIGRATION_SQL = """
INSERT INTO salary_benchmarks (role_title, seniority, location, currency, p25, p50, p75, p90, sample_size, source) VALUES
    ('Software Engineer', 'junior',    'Eindhoven', 'EUR', 42000, 48000, 54000, 60000, 120, 'GSP Internal 2024'),
    ('Software Engineer', 'mid',       'Eindhoven', 'EUR', 54000, 62000, 70000, 80000, 250, 'GSP Internal 2024'),
    ('Software Engineer', 'senior',    'Eindhoven', 'EUR', 70000, 82000, 95000, 110000, 180, 'GSP Internal 2024'),
    ('Software Engineer', 'lead',      'Eindhoven', 'EUR', 85000, 98000, 115000, 130000, 60, 'GSP Internal 2024'),
    ('Embedded Software Engineer', 'junior', 'Eindhoven', 'EUR', 44000, 50000, 56000, 62000, 90, 'GSP Internal 2024'),
    ('Embedded Software Engineer', 'mid',    'Eindhoven', 'EUR', 56000, 65000, 74000, 85000, 140, 'GSP Internal 2024'),
    ('Embedded Software Engineer', 'senior', 'Eindhoven', 'EUR', 72000, 85000, 98000, 115000, 100, 'GSP Internal 2024'),
    ('C++ Developer', 'mid',    'Eindhoven', 'EUR', 58000, 68000, 78000, 90000, 110, 'GSP Internal 2024'),
    ('C++ Developer', 'senior', 'Eindhoven', 'EUR', 74000, 88000, 102000, 118000, 80, 'GSP Internal 2024'),
    ('Python Developer', 'junior', 'Eindhoven', 'EUR', 40000, 46000, 52000, 58000, 95, 'GSP Internal 2024'),
    ('Python Developer', 'mid',    'Eindhoven', 'EUR', 52000, 60000, 70000, 82000, 160, 'GSP Internal 2024'),
    ('Python Developer', 'senior', 'Eindhoven', 'EUR', 68000, 80000, 93000, 108000, 110, 'GSP Internal 2024'),
    ('DevOps Engineer', 'mid',    'Eindhoven', 'EUR', 56000, 65000, 75000, 88000, 85, 'GSP Internal 2024'),
    ('DevOps Engineer', 'senior', 'Eindhoven', 'EUR', 72000, 84000, 97000, 112000, 55, 'GSP Internal 2024'),
    ('Data Engineer', 'mid',    'Eindhoven', 'EUR', 54000, 63000, 73000, 85000, 70, 'GSP Internal 2024'),
    ('Data Engineer', 'senior', 'Eindhoven', 'EUR', 70000, 82000, 95000, 110000, 45, 'GSP Internal 2024'),
    ('Machine Learning Engineer', 'mid',    'Eindhoven', 'EUR', 58000, 70000, 82000, 96000, 50, 'GSP Internal 2024'),
    ('Machine Learning Engineer', 'senior', 'Eindhoven', 'EUR', 78000, 92000, 108000, 125000, 35, 'GSP Internal 2024'),
    ('Test Engineer', 'junior', 'Eindhoven', 'EUR', 38000, 44000, 50000, 56000, 80, 'GSP Internal 2024'),
    ('Test Engineer', 'mid',    'Eindhoven', 'EUR', 48000, 56000, 65000, 75000, 110, 'GSP Internal 2024'),
    ('Test Engineer', 'senior', 'Eindhoven', 'EUR', 62000, 72000, 84000, 97000, 70, 'GSP Internal 2024'),
    ('Scrum Master', 'mid',    'Eindhoven', 'EUR', 55000, 65000, 76000, 88000, 60, 'GSP Internal 2024'),
    ('Product Manager', 'mid',    'Eindhoven', 'EUR', 60000, 72000, 85000, 100000, 55, 'GSP Internal 2024'),
    ('Product Manager', 'senior', 'Eindhoven', 'EUR', 78000, 92000, 108000, 125000, 35, 'GSP Internal 2024'),
    ('Engineering Manager', 'senior', 'Eindhoven', 'EUR', 90000, 108000, 128000, 150000, 30, 'GSP Internal 2024'),
    ('Software Engineer', 'junior',    'Remote', 'EUR', 38000, 44000, 52000, 60000, 80, 'GSP Internal 2024'),
    ('Software Engineer', 'mid',       'Remote', 'EUR', 50000, 58000, 68000, 80000, 130, 'GSP Internal 2024'),
    ('Software Engineer', 'senior',    'Remote', 'EUR', 66000, 78000, 92000, 108000, 90, 'GSP Internal 2024')
ON CONFLICT DO NOTHING;
"""

if __name__ == "__main__":
    import asyncio
    import asyncpg
    import os

    host = os.getenv("POSTGRES_HOST", "localhost")
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    db = os.getenv("POSTGRES_DB", "recruitment_db")
    user = os.getenv("POSTGRES_USER", "talentos_admin")
    password = os.getenv("POSTGRES_PASSWORD", "")

    async def run():
        conn = await asyncpg.connect(host=host, port=port, database=db, user=user, password=password)
        try:
            await conn.execute(MIGRATION_SQL)
            print("Migration 009 completed: salary_benchmarks seeded.")
        finally:
            await conn.close()

    asyncio.run(run())
