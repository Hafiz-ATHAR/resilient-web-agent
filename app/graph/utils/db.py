import aiosqlite

db_path = "state-db/long-running-job.db"
sqlite_connection = aiosqlite.connect(db_path, check_same_thread=False)
