"""Interactive, server-local first-administrator initialization; no public signup privilege."""
import getpass
import uuid
import app


def main():
    username = app.normalize_username(input('Administrator username: '))
    password = getpass.getpass('Password (at least 12 characters): ')
    if len(password) < 12 or password != getpass.getpass('Repeat password: '):
        raise SystemExit('Password too short or confirmation mismatch.')
    with app.db_connect() as conn:
        if conn.execute("SELECT id FROM users WHERE role='admin' AND is_active=1").fetchone():
            raise SystemExit('An active administrator exists. Use account management to authorize more administrators.')
        if conn.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone():
            raise SystemExit('Username already exists. Choose a new administrator username; existing accounts are never promoted automatically.')
        salt, digest = app.password_hash(password)
        conn.execute('INSERT INTO users (id,username,display_name,password_salt,password_hash,role,is_active,created_at,updated_at) VALUES (?,?,?,?,?,?,1,?,?)',
                     (uuid.uuid4().hex, username, username, salt, digest, 'admin', app.iso_now(), app.iso_now()))
    print('Administrator created. Sign in using the website.')


if __name__ == '__main__':
    main()
