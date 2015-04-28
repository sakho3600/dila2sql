# encoding: utf8

# This file is part of a program licensed under the terms of the GNU
# General Public License version 3 (or at your option any later version)
# as published by the Free Software Foundation: http://www.gnu.org/licenses/


from __future__ import print_function, unicode_literals

from argparse import ArgumentParser
from sqlite3 import OperationalError

from utils import connect_db, input


def connect_by_nature_num():
    db.run("""
        UPDATE textes_versions
           SET texte_id = (
                   SELECT id
                     FROM textes t
                    WHERE t.nature = textes_versions.nature
                      AND t.num = textes_versions.num
               )
         WHERE texte_id IS NULL
           AND EXISTS (
                   SELECT id
                     FROM textes t
                    WHERE t.nature = textes_versions.nature
                      AND t.num = textes_versions.num
               );
    """)
    print('connected %i rows of textes_versions based on (nature, num)' % db.changes())

def connect_by_nor():
    db.run("""
        CREATE TEMP TABLE texte_by_nor AS
            SELECT nor, min(texte_id)
              FROM textes_versions
             WHERE nor IS NOT NULL
               AND texte_id IS NOT NULL
          GROUP BY nor
            HAVING min(nature) = max(nature)
               AND min(num) = max(num)
               AND min(texte_id) = max(texte_id);
    """)
    db.run("CREATE UNIQUE INDEX texte_by_nor_index ON texte_by_nor (nor)")
    db.run("""
        UPDATE textes_versions
           SET texte_id = (
                   SELECT texte_id
                     FROM texte_by_nor t
                    WHERE t.nor = textes_versions.nor
               )
         WHERE texte_id IS NULL
           AND EXISTS (
                   SELECT texte_id
                     FROM texte_by_nor t
                    WHERE t.nor = textes_versions.nor
               );
    """)
    print('connected %i rows of textes_versions based on nor' % db.changes())
    db.run("DROP TABLE texte_by_nor")

def connect_by_titrefull_s():
    db.run("""
        CREATE TEMP TABLE texte_by_titrefull_s AS
            SELECT DISTINCT titrefull_s, texte_id
              FROM textes_versions
             WHERE texte_id IS NOT NULL;
    """)
    db.run("CREATE UNIQUE INDEX texte_by_titrefull_s_index ON texte_by_titrefull_s (titrefull_s)")
    db.run("""
        UPDATE textes_versions
           SET texte_id = (
                   SELECT texte_id
                     FROM texte_by_titrefull_s t
                    WHERE t.titrefull_s = textes_versions.titrefull_s
               )
         WHERE texte_id IS NULL
           AND EXISTS (
                   SELECT texte_id
                     FROM texte_by_titrefull_s t
                    WHERE t.titrefull_s = textes_versions.titrefull_s
               );
    """)
    print('connected %i rows of textes_versions based on titrefull_s' % db.changes())
    db.run("DROP TABLE texte_by_titrefull_s")


def factorize_by(key):
    duplicates = db.all("""
        SELECT min(nature), {0}, group_concat(texte_id)
          FROM textes_versions
         WHERE texte_id IS NOT NULL
      GROUP BY {0}
        HAVING min(texte_id) <> max(texte_id)
           AND min(nature) = max(nature)
    """.format(key))
    total = 0
    factorized = 0
    for row in duplicates:
        ids = tuple(row[2].split(','))
        db.run("INSERT INTO textes (nature, {0}) VALUES (?, ?)".format(key),
               (row[0], row[1]))
        uid = db.one("SELECT id FROM textes WHERE {0} = ?".format(key), (row[1],))
        db.run("""
            UPDATE textes_versions
               SET texte_id = %s
             WHERE texte_id IN (%s);
        """ % (uid, row[2]))
        total += len(ids)
        factorized += 1
    print('factorized %i duplicates into %i uniques based on %s' % (total, factorized, key))


def main():
    db.run("""
        CREATE TABLE IF NOT EXISTS textes
        ( id integer primary key not null
        , nature text not null
        , num text
        , nor char(12) unique -- only used during factorization
        , titrefull_s text unique -- only used during factorization
        , UNIQUE (nature, num)
        );
    """)
    try:
        db.run("ALTER TABLE textes_versions ADD COLUMN texte_id integer REFERENCES textes")
        db.run("CREATE INDEX textes_versions_texte_id ON textes_versions (texte_id)")
    except OperationalError:
        pass

    connect_by_nature_num()

    db.run("""
        INSERT INTO textes (nature, num)
             SELECT nature, num
               FROM textes_versions
              WHERE texte_id IS NULL
                AND nature IS NOT NULL
                AND num IS NOT NULL
           GROUP BY nature, num;
    """)
    print('inserted %i rows in textes based on (nature, num)' % db.changes())

    connect_by_nature_num()
    connect_by_nor()
    connect_by_titrefull_s()

    db.run("""
        INSERT INTO textes (nature, nor)
            SELECT nature, nor
              FROM textes_versions
             WHERE texte_id IS NULL
               AND nor IS NOT NULL
          GROUP BY nor
            HAVING min(nature) = max(nature)
               AND min(titrefull_s) = max(titrefull_s);
    """)
    print('inserted %i rows in textes based on nor' % db.changes())

    db.run("""
        UPDATE textes_versions
           SET texte_id = (
                   SELECT id
                     FROM textes t
                    WHERE t.nor = textes_versions.nor
               )
         WHERE texte_id IS NULL
           AND EXISTS (
                   SELECT id
                     FROM textes t
                    WHERE t.nor = textes_versions.nor
               );
    """)
    print('connected %i rows of textes_versions based on nor' % db.changes())

    factorize_by('titrefull_s')
    connect_by_titrefull_s()

    db.run("""
        INSERT INTO textes (nature, titrefull_s)
            SELECT nature, titrefull_s
              FROM textes_versions
             WHERE texte_id IS NULL
          GROUP BY titrefull_s;
    """)
    print('inserted %i rows in textes based on titrefull_s' % db.changes())

    db.run("""
        UPDATE textes_versions
           SET texte_id = (
                   SELECT id
                     FROM textes t
                    WHERE t.titrefull_s = textes_versions.titrefull_s
               )
         WHERE texte_id IS NULL
           AND EXISTS (
                   SELECT id
                     FROM textes t
                    WHERE t.titrefull_s = textes_versions.titrefull_s
               );
    """)
    print('connected %i rows of textes_versions based on titrefull_s' % db.changes())

    # Clean up factorized texts
    db.run("""
        DELETE FROM textes
         WHERE NOT EXISTS (
                   SELECT *
                     FROM textes_versions
                    WHERE texte_id = textes.id
               )
    """)
    print('deleted %i unused rows from textes' % db.changes())

    left = db.one("SELECT count(*) FROM textes_versions WHERE texte_id IS NULL")
    if left != 0:
        print("Fail: %i rows haven't been connected")
    else:
        # SQLite doesn't implement DROP COLUMN so we just nullify them instead
        db.run("UPDATE textes SET nor = NULL, titrefull_s = NULL")
        print("done")


if __name__ == '__main__':
    p = ArgumentParser()
    p.add_argument('db')
    args = p.parse_args()

    db = connect_db(args.db)
    try:
        with db:
            main()
            save = input('Sauvegarder les modifications? (o/n) ')
            if save.lower() != 'o':
                raise KeyboardInterrupt
    except KeyboardInterrupt:
        pass