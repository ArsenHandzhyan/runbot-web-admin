#!/usr/bin/env python3
"""
Migration script for challenge_registrations and event_registrations tables
Migrates data from Render PostgreSQL to Supabase
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import os
import sys

def migrate_registrations():
    print("=" * 80)
    print("МИГРАЦИЯ РЕГИСТРАЦИЙ")
    print("=" * 80)

    # URLs баз данных
    render_url = "postgresql://runbot:MMJntms3At5ydvbRcyv1x3l5Yq8dgSUR@dpg-d5maq1f5r7bs73d13c30-a/runbot_tp8c"
    supabase_url = "postgresql://postgres.dapbbiuzazcxogxitbrg:yuGeh2czvOgLaHjK@aws-1-eu-north-1.pooler.supabase.com:5432/postgres"

    try:
        # Подключаемся к обеим базам
        print("\n1. Подключение к Render (старая база)...")
        render_conn = psycopg2.connect(render_url)
        print("   ✓ Подключено к Render")

        print("\n2. Подключение к Supabase (новая база)...")
        supabase_conn = psycopg2.connect(supabase_url)
        print("   ✓ Подключено к Supabase")

        render_cur = render_conn.cursor(cursor_factory=RealDictCursor)
        supabase_cur = supabase_conn.cursor()

        # Миграция challenge_registrations
        print("\n" + "=" * 80)
        print("Миграция challenge_registrations")
        print("=" * 80)

        render_cur.execute("SELECT * FROM challenge_registrations ORDER BY id;")
        challenge_regs = render_cur.fetchall()
        print(f"Найдено в Render: {len(challenge_regs)} записей")

        migrated_cr = 0
        for reg in challenge_regs:
            try:
                supabase_cur.execute("""
                    INSERT INTO challenge_registrations (id, participant_id, challenge_id, registration_date, is_active)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        participant_id = EXCLUDED.participant_id,
                        challenge_id = EXCLUDED.challenge_id,
                        registration_date = EXCLUDED.registration_date,
                        is_active = EXCLUDED.is_active
                """, (reg['id'], reg['participant_id'], reg['challenge_id'], reg['registration_date'], reg['is_active']))
                migrated_cr += 1
                print(f"  ✓ ID {reg['id']}: Participant {reg['participant_id']} → Challenge {reg['challenge_id']}")
            except Exception as e:
                print(f"  ✗ Ошибка для ID {reg['id']}: {e}")

        supabase_conn.commit()
        print(f"\n✓ Мигрировано challenge_registrations: {migrated_cr}/{len(challenge_regs)}")

        # Миграция event_registrations
        print("\n" + "=" * 80)
        print("Миграция event_registrations")
        print("=" * 80)

        render_cur.execute("SELECT * FROM event_registrations ORDER BY id;")
        event_regs = render_cur.fetchall()
        print(f"Найдено в Render: {len(event_regs)} записей")

        migrated_er = 0
        for reg in event_regs:
            try:
                supabase_cur.execute("""
                    INSERT INTO event_registrations (id, participant_id, event_id, registration_date)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        participant_id = EXCLUDED.participant_id,
                        event_id = EXCLUDED.event_id,
                        registration_date = EXCLUDED.registration_date
                """, (reg['id'], reg['participant_id'], reg['event_id'], reg['registration_date']))
                migrated_er += 1
                print(f"  ✓ ID {reg['id']}: Participant {reg['participant_id']} → Event {reg['event_id']}")
            except Exception as e:
                print(f"  ✗ Ошибка для ID {reg['id']}: {e}")

        supabase_conn.commit()
        print(f"\n✓ Мигрировано event_registrations: {migrated_er}/{len(event_regs)}")

        print("\n" + "=" * 80)
        print("ИТОГО")
        print("=" * 80)
        print(f"Challenge registrations: {migrated_cr}/{len(challenge_regs)}")
        print(f"Event registrations: {migrated_er}/{len(event_regs)}")
        print("\n✓ Миграция завершена успешно!")

        return True

    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        try:
            render_cur.close()
            render_conn.close()
            supabase_cur.close()
            supabase_conn.close()
            print("\n✓ Соединения закрыты")
        except:
            pass

if __name__ == "__main__":
    success = migrate_registrations()
    sys.exit(0 if success else 1)
