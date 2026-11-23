"""Account-scoped interface language, shared by SQLite and MySQL deployments."""
from fastapi import Depends
from pydantic import BaseModel, constr


class LanguagePreference(BaseModel):
    language: constr(regex=r'^(en|zh)$')

    class Config:
        extra = 'forbid'


def install_user_preferences(app, h):
    db, auth = h['db_connect'], h['get_current_user']
    with db() as conn:
        conn.execute(f'''CREATE TABLE IF NOT EXISTS user_preferences (
            user_id {h['ID_SQL']} PRIMARY KEY,
            language {h['SHORT_SQL']} NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        ){h['TABLE_OPTIONS']}''')

    @app.get('/api/account/preferences')
    def read(user=Depends(auth)):
        with db() as conn:
            row = conn.execute('SELECT language FROM user_preferences WHERE user_id=?', (user['id'],)).fetchone()
        return {'language': row['language'] if row else None}

    @app.put('/api/account/preferences')
    def update(payload: LanguagePreference, user=Depends(auth)):
        with db() as conn:
            if h['DB_ENGINE'] == 'mysql':
                conn.execute('''INSERT INTO user_preferences (user_id,language) VALUES (?,?)
                                ON DUPLICATE KEY UPDATE language=VALUES(language)''', (user['id'], payload.language))
            else:
                conn.execute('''INSERT INTO user_preferences (user_id,language) VALUES (?,?)
                                ON CONFLICT(user_id) DO UPDATE SET language=excluded.language''', (user['id'], payload.language))
        return {'language': payload.language}
