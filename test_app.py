import io
import os
import sqlite3
import unittest
import uuid

import app as app_module


class GrievanceSystemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = app_module.app.test_client()
        cls.admin_email = 'admin@resolveai.local'
        cls.admin_password = 'Admin@123'

    def unique_email(self, prefix='citizen'):
        return f'{prefix}+{uuid.uuid4().hex[:8]}@example.com'

    def test_01_citizen_registration_and_login(self):
        email = self.unique_email('citizen')
        response = self.client.post('/api/register', json={
            'name': 'Test Citizen',
            'email': email,
            'password': 'securepass123',
        })
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn('token', data)
        self.assertEqual(data['user']['email'], email)

        login_response = self.client.post('/api/login', json={
            'email': email,
            'password': 'securepass123',
            'role': 'citizen',
        })
        self.assertEqual(login_response.status_code, 200)
        self.assertIn('token', login_response.get_json())

    def test_02_citizen_complaint_submission_and_ai_prediction(self):
        email = self.unique_email('complaint')
        location = f'Block A {uuid.uuid4().hex[:8]}'
        register = self.client.post('/api/register', json={
            'name': 'Complaint User',
            'email': email,
            'password': 'securepass123',
        })
        token = register.get_json()['token']

        response = self.client.post('/api/complaints', json={
            'title': 'No water supply for two days',
            'description': 'Water has not been supplied at my area for two days and it is affecting residents.',
            'category': 'Water Supply',
            'location': location,
            'evidence': 'photo.png',
        }, headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['complaint']['id'].startswith('GRV-'))
        self.assertEqual(data['prediction']['predicted_category'], 'Water Supply')
        self.assertIn(data['prediction']['recommended_department'], ['Water Supply Department'])

    def test_02b_duplicate_problem_at_same_location_is_rejected(self):
        location = f'North Gate Block A {uuid.uuid4().hex[:8]}'
        citizen = self.client.post('/api/register', json={
            'name': 'Duplicate Test Citizen',
            'email': self.unique_email('duplicate'),
            'password': 'securepass123',
        }).get_json()
        headers = {'Authorization': f'Bearer {citizen["token"]}'}
        complaint = {
            'title': 'Street light not working',
            'description': 'The street light is broken and the road is dark.',
            'category': 'Street Lighting',
            'location': location,
        }

        first = self.client.post('/api/complaints', json=complaint, headers=headers)
        self.assertEqual(first.status_code, 200)

        duplicate = self.client.post('/api/complaints', json={
            **complaint,
            'title': 'street-light not working!',
            'location': f' {location.lower()} ',
        }, headers=headers)
        self.assertEqual(duplicate.status_code, 409)
        self.assertIn('already been submitted', duplicate.get_json()['error'])

        different_location = self.client.post('/api/complaints', json={
            **complaint,
            'location': f'South Gate Block A {uuid.uuid4().hex[:8]}',
        }, headers=headers)
        self.assertEqual(different_location.status_code, 200)

        independent_citizen = self.client.post('/api/register', json={
            'name': 'Independent Reporter',
            'email': self.unique_email('independent'),
            'password': 'securepass123',
        }).get_json()
        independent_report = self.client.post(
            '/api/complaints',
            json=complaint,
            headers={'Authorization': f'Bearer {independent_citizen["token"]}'},
        )
        self.assertEqual(independent_report.status_code, 200)

    def test_02c_evidence_upload_and_access_control(self):
        citizen = self.client.post('/api/register', json={
            'name': 'Evidence Owner',
            'email': self.unique_email('evidenceowner'),
            'password': 'securepass123',
        }).get_json()
        owner_headers = {'Authorization': f'Bearer {citizen["token"]}'}
        evidence_bytes = b'%PDF-1.4 sample evidence'
        response = self.client.post('/api/complaints', data={
            'title': 'Evidence upload verification',
            'description': 'A report with attached PDF evidence.',
            'category': 'Other',
            'location': f'Evidence test location {uuid.uuid4().hex[:8]}',
            'evidence': (io.BytesIO(evidence_bytes), 'proof.pdf'),
        }, headers=owner_headers, content_type='multipart/form-data')
        self.assertEqual(response.status_code, 200)
        complaint_id = response.get_json()['complaint']['id']

        download = self.client.get(f'/api/complaints/{complaint_id}/evidence', headers=owner_headers)
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.data, evidence_bytes)
        evidence_path = response.get_json()['complaint']['evidence']
        public_download = self.client.get(f'/{evidence_path}')
        self.assertEqual(public_download.status_code, 404)
        download.close()

        other_citizen = self.client.post('/api/register', json={
            'name': 'Other Citizen',
            'email': self.unique_email('evidenceother'),
            'password': 'securepass123',
        }).get_json()
        denied = self.client.get(
            f'/api/complaints/{complaint_id}/evidence',
            headers={'Authorization': f'Bearer {other_citizen["token"]}'},
        )
        self.assertEqual(denied.status_code, 403)

        admin_login = self.client.post('/api/login', json={
            'email': self.admin_email,
            'password': self.admin_password,
            'role': 'admin',
        })
        admin_download = self.client.get(
            f'/api/complaints/{complaint_id}/evidence',
            headers={'Authorization': f'Bearer {admin_login.get_json()["token"]}'},
        )
        self.assertEqual(admin_download.status_code, 200)
        admin_download.close()

        invalid = self.client.post('/api/complaints', data={
            'title': 'Invalid evidence upload',
            'description': 'Executable attachments must be rejected.',
            'category': 'Other',
            'location': f'Invalid evidence location {uuid.uuid4().hex[:8]}',
            'evidence': (io.BytesIO(b'not allowed'), 'payload.exe'),
        }, headers=owner_headers, content_type='multipart/form-data')
        self.assertEqual(invalid.status_code, 400)

    def test_03_citizen_cannot_access_admin_routes(self):
        email = self.unique_email('citizen2')
        register = self.client.post('/api/register', json={
            'name': 'Restricted User',
            'email': email,
            'password': 'securepass123',
        })
        token = register.get_json()['token']

        response = self.client.get('/api/admin/dashboard', headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(response.status_code, 403)

    def test_04_admin_can_view_and_update_complaint(self):
        admin_login = self.client.post('/api/login', json={
            'email': self.admin_email,
            'password': self.admin_password,
            'role': 'admin',
        })
        admin_token = admin_login.get_json()['token']

        email = self.unique_email('adminview')
        location = f'Gate area {uuid.uuid4().hex[:8]}'
        citizen = self.client.post('/api/register', json={
            'name': 'Admin Test Citizen',
            'email': email,
            'password': 'securepass123',
        }).get_json()
        citizen_token = citizen['token']

        complaint_response = self.client.post('/api/complaints', json={
            'title': 'Street light not working',
            'description': 'Street light near the gate is not working and is unsafe at night.',
            'category': 'Street Lighting',
            'location': location,
            'evidence': '',
        }, headers={'Authorization': f'Bearer {citizen_token}'})
        complaint_id = complaint_response.get_json()['complaint']['id']

        update = self.client.patch(f'/api/admin/complaints/{complaint_id}', json={
            'status': 'In Progress',
            'department': 'Electrical & Street Lighting Department',
            'assigned_officer': 'Officer Asha',
            'priority': 'High',
            'resolution': 'Crew dispatched for repair.',
            'reason': 'Admin updated the complaint status.'
        }, headers={'Authorization': f'Bearer {admin_token}'})
        self.assertEqual(update.status_code, 200)
        self.assertEqual(update.get_json()['complaint']['status'], 'In Progress')
        self.assertEqual(update.get_json()['complaint']['assigned_officer'], 'Officer Asha')

    def test_05_overdue_escalation_works(self):
        location = f'Main road {uuid.uuid4().hex[:8]}'
        email = self.unique_email('overdue')
        citizen = self.client.post('/api/register', json={
            'name': 'Overdue User',
            'email': email,
            'password': 'securepass123',
        }).get_json()
        token = citizen['token']
        complaint_response = self.client.post('/api/complaints', json={
            'title': 'Drainage overflow',
            'description': 'The main drain has been overflowing for several days and has become a health issue.',
            'category': 'Drainage',
            'location': location,
            'evidence': '',
        }, headers={'Authorization': f'Bearer {token}'})
        complaint_id = complaint_response.get_json()['complaint']['id']

        conn = sqlite3.connect(app_module.DB_PATH)
        conn.execute(
            "UPDATE complaints SET status = 'Pending', deadline = ?, updated_at = ? WHERE complaint_id = ?",
            ('2020-01-01T00:00:00Z', '2020-01-01T00:00:00Z', complaint_id),
        )
        conn.commit()
        conn.close()

        app_module.process_overdue_complaints()

        conn = sqlite3.connect(app_module.DB_PATH)
        row = conn.execute('SELECT status, escalation_reason FROM complaints WHERE complaint_id = ?', (complaint_id,)).fetchone()
        escalations = conn.execute('SELECT COUNT(*) FROM escalations WHERE complaint_id = ?', (complaint_id,)).fetchone()[0]
        conn.close()
        self.assertEqual(row[0], 'Escalated')
        self.assertGreaterEqual(escalations, 1)

    def create_reward_citizen(self, name='Reward Citizen'):
        return self.client.post('/api/register', json={
            'name': name,
            'email': self.unique_email('reward'),
            'password': 'securepass123',
        }).get_json()

    def login_reward_admin(self):
        response = self.client.post('/api/login', json={
            'email': self.admin_email,
            'password': self.admin_password,
            'role': 'admin',
        })
        self.assertEqual(response.status_code, 200)
        return {'Authorization': f'Bearer {response.get_json()["token"]}'}

    def submit_reward_complaint(self, headers, with_evidence=False):
        payload = {
            'title': f'Community street light issue {uuid.uuid4().hex[:8]}',
            'description': 'A street light is broken and this location is unsafe after dark.',
            'category': 'Street Lighting',
            'location': f'Reward location {uuid.uuid4().hex[:8]}',
        }
        if with_evidence:
            response = self.client.post('/api/complaints', data={
                **payload,
                'evidence': (io.BytesIO(b'%PDF-1.4 civic evidence'), 'evidence.pdf'),
            }, headers=headers, content_type='multipart/form-data')
        else:
            response = self.client.post('/api/complaints', json=payload, headers=headers)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()['complaint']

    def test_06_rewards_require_admin_verification_and_awards_are_idempotent(self):
        citizen = self.create_reward_citizen()
        citizen_headers = {'Authorization': f'Bearer {citizen["token"]}'}
        complaint = self.submit_reward_complaint(citizen_headers)
        admin_headers = self.login_reward_admin()

        initial = self.client.get('/api/citizen/rewards', headers=citizen_headers).get_json()
        self.assertEqual(initial['summary']['available_points'], 0)
        self.assertEqual(initial['summary']['verified_contributions'], 0)

        forbidden = self.client.post(
            f'/api/admin/rewards/complaints/{complaint["id"]}/decision',
            json={'eligible': True, 'reason': 'Should not be allowed'},
            headers=citizen_headers,
        )
        self.assertEqual(forbidden.status_code, 403)

        original_priority = complaint['priority']
        original_deadline = complaint['deadline']
        original_department = complaint['department']
        decision = {'eligible': True, 'reason': 'Evidence shows a genuine public lighting issue.'}
        for _ in range(2):
            result = self.client.post(
                f'/api/admin/rewards/complaints/{complaint["id"]}/decision',
                json=decision,
                headers=admin_headers,
            )
            self.assertEqual(result.status_code, 200, result.get_json())

        summary = self.client.get('/api/citizen/rewards', headers=citizen_headers).get_json()
        self.assertEqual(summary['summary']['available_points'], 10)
        self.assertEqual(summary['summary']['verified_contributions'], 1)
        self.assertEqual(summary['badges'][0]['badge_key'], 'civic_starter')
        self.assertEqual(sum(row['points'] for row in summary['transactions']), 10)

        detail = self.client.get(f'/api/complaints/{complaint["id"]}', headers=citizen_headers).get_json()['complaint']
        self.assertEqual(detail['priority'], original_priority)
        self.assertEqual(detail['deadline'], original_deadline)
        self.assertEqual(detail['department'], original_department)

        other_citizen = self.create_reward_citizen('Private History Owner')
        other_headers = {'Authorization': f'Bearer {other_citizen["token"]}'}
        private = self.client.get('/api/citizen/rewards?user_id=' + str(citizen['user']['id']), headers=other_headers).get_json()
        self.assertEqual(private['summary']['available_points'], 0)

        self.assertEqual(self.client.post('/api/citizen/rewards', json={'points': 999}, headers=citizen_headers).status_code, 405)
        self.assertEqual(self.client.post('/api/admin/rewards/adjustments', json={'citizen_id': citizen['user']['id'], 'points': 10, 'reason': 'Self award attempt'}, headers=citizen_headers).status_code, 403)
        self.assertEqual(self.client.post('/api/admin/rewards/adjustments', json={'citizen_id': citizen['user']['id'], 'points': -100, 'reason': 'Invalid overdraw'}, headers=admin_headers).status_code, 400)

        adjustment_key = f'test-adjustment-{uuid.uuid4().hex}'
        admin_adjustment = self.client.post('/api/admin/rewards/adjustments', json={
            'citizen_id': citizen['user']['id'],
            'points': 3,
            'complaint_id': complaint['id'],
            'reason': 'Administrative ledger correction.',
            'idempotency_key': adjustment_key,
        }, headers=admin_headers)
        self.assertEqual(admin_adjustment.status_code, 201)
        repeated_adjustment = self.client.post('/api/admin/rewards/adjustments', json={
            'citizen_id': citizen['user']['id'],
            'points': 3,
            'complaint_id': complaint['id'],
            'reason': 'Administrative ledger correction.',
            'idempotency_key': adjustment_key,
        }, headers=admin_headers)
        self.assertEqual(repeated_adjustment.status_code, 409)
        adjustment_row = self.client.get('/api/admin/rewards/transactions', headers=admin_headers).get_json()['transactions'][0]
        self.assertEqual(adjustment_row['authorized_by'], self.client.get('/api/profile', headers=admin_headers).get_json()['user']['id'])
        self.assertEqual(adjustment_row['points'], 3)

    def test_07_evidence_update_resolution_and_reversal_are_auditable(self):
        citizen = self.create_reward_citizen('Contribution Citizen')
        headers = {'Authorization': f'Bearer {citizen["token"]}'}
        admin_headers = self.login_reward_admin()
        complaint = self.submit_reward_complaint(headers, with_evidence=True)

        initial = self.client.get('/api/citizen/rewards', headers=headers).get_json()
        self.assertEqual(initial['summary']['available_points'], 0)

        update_response = self.client.post(
            f'/api/complaints/{complaint["id"]}/updates',
            json={'details': 'The light has also failed on the neighboring pole, and residents report the outage begins at dusk.'},
            headers=headers,
        )
        self.assertEqual(update_response.status_code, 201)
        update_id = update_response.get_json()['update_id']
        repeated_update = self.client.post(
            f'/api/complaints/{complaint["id"]}/updates',
            json={'details': 'The light has also failed on the neighboring pole, and residents report the outage begins at dusk.'},
            headers=headers,
        )
        self.assertEqual(repeated_update.status_code, 409)

        complaint_review = self.client.post(
            f'/api/admin/rewards/complaints/{complaint["id"]}/decision',
            json={'eligible': True, 'evidence_approved': True, 'reason': 'Original report and attached evidence are useful.'},
            headers=admin_headers,
        )
        self.assertEqual(complaint_review.status_code, 200, complaint_review.get_json())
        self.assertEqual(self.client.get('/api/citizen/rewards', headers=headers).get_json()['summary']['available_points'], 15)

        update_decision = {'verified': True, 'reason': 'Update adds actionable information.'}
        for _ in range(2):
            self.assertEqual(self.client.post(f'/api/admin/rewards/updates/{update_id}/decision', json=update_decision, headers=admin_headers).status_code, 200)
        self.assertEqual(self.client.get('/api/citizen/rewards', headers=headers).get_json()['summary']['available_points'], 20)

        admin_update = self.client.patch(
            f'/api/admin/complaints/{complaint["id"]}',
            json={'status': 'Resolved', 'resolution': 'The damaged fixture was repaired and tested.'},
            headers=admin_headers,
        )
        self.assertEqual(admin_update.status_code, 200)
        resolved_review = self.client.post(
            f'/api/admin/rewards/complaints/{complaint["id"]}/decision',
            json={'eligible': True, 'evidence_approved': True, 'resolution_verified': True, 'reason': 'Repair was confirmed on site.'},
            headers=admin_headers,
        )
        self.assertEqual(resolved_review.status_code, 200, resolved_review.get_json())
        summary = self.client.get('/api/citizen/rewards', headers=headers).get_json()
        self.assertEqual(summary['summary']['available_points'], 40)
        self.assertEqual(summary['summary']['verified_resolutions'], 1)

        award = next(row for row in summary['transactions'] if row['event_type'] == 'verified_contribution')
        reversal = self.client.post(
            f'/api/admin/rewards/transactions/{award["transaction_id"]}/reverse',
            json={'reason': 'Later review found the original evidence insufficient.'},
            headers=admin_headers,
        )
        self.assertEqual(reversal.status_code, 200)
        repeated_reversal = self.client.post(
            f'/api/admin/rewards/transactions/{award["transaction_id"]}/reverse',
            json={'reason': 'Attempt to reverse the same award again.'},
            headers=admin_headers,
        )
        self.assertEqual(repeated_reversal.status_code, 409)
        after_reversal = self.client.get('/api/citizen/rewards', headers=headers).get_json()
        self.assertEqual(after_reversal['summary']['available_points'], 30)
        self.assertTrue(any(row['event_type'] == 'reversal' and row['points'] == -10 for row in after_reversal['transactions']))

    def test_08_reward_rejection_leaderboard_privacy_and_config(self):
        citizen = self.create_reward_citizen('Private Person Name')
        headers = {'Authorization': f'Bearer {citizen["token"]}'}
        admin_headers = self.login_reward_admin()
        complaint = self.submit_reward_complaint(headers)
        rejected = self.client.post(
            f'/api/admin/rewards/complaints/{complaint["id"]}/decision',
            json={'eligible': False, 'reason': 'This report could not be validated.'},
            headers=admin_headers,
        )
        self.assertEqual(rejected.status_code, 200)
        summary = self.client.get('/api/citizen/rewards', headers=headers).get_json()
        self.assertEqual(summary['summary']['available_points'], 0)
        self.assertEqual(summary['summary']['verified_contributions'], 0)

        self.assertEqual(self.client.patch(
            f'/api/admin/complaints/{complaint["id"]}',
            json={'status': 'Rejected'},
            headers=admin_headers,
        ).status_code, 200)
        invalid_approval = self.client.post(
            f'/api/admin/rewards/complaints/{complaint["id"]}/decision',
            json={'eligible': True, 'reason': 'Rejected complaint must not qualify.'},
            headers=admin_headers,
        )
        self.assertEqual(invalid_approval.status_code, 400)
        self.assertEqual(self.client.get('/api/citizen/leaderboard', headers=headers).status_code, 404)

        config_before = self.client.get('/api/admin/rewards/config', headers=admin_headers).get_json()
        original_rule = next(rule for rule in config_before['rules'] if rule['rule_key'] == 'verified_contribution')
        configurable = self.client.patch('/api/admin/rewards/config', json={
            'rules': {'verified_contribution': {'points': original_rule['points'] + 1, 'enabled': True}},
            'badges': {'civic_starter': 2},
        }, headers=admin_headers)
        self.assertEqual(configurable.status_code, 200, configurable.get_json())
        self.assertEqual(next(rule for rule in configurable.get_json()['rules'] if rule['rule_key'] == 'verified_contribution')['points'], original_rule['points'] + 1)
        self.assertEqual(next(badge for badge in configurable.get_json()['badges'] if badge['badge_key'] == 'civic_starter')['contribution_threshold'], 2)
        self.assertEqual(self.client.patch('/api/admin/rewards/config', json={
            'rules': {'verified_contribution': {'points': original_rule['points'], 'enabled': bool(original_rule['enabled'])}},
            'badges': {'civic_starter': 1},
        }, headers=admin_headers).status_code, 200)
        config_enabled = self.client.patch('/api/admin/rewards/config', json={'leaderboard_enabled': True}, headers=admin_headers)
        self.assertEqual(config_enabled.status_code, 200, config_enabled.get_json())
        config_after = config_enabled.get_json()
        self.assertTrue(config_after['leaderboard_enabled'])
        self.assertTrue(all('email' not in entry and 'description' not in entry for entry in self.client.get('/api/citizen/leaderboard', headers=headers).get_json()['leaderboard']))
        self.assertEqual(self.client.patch('/api/admin/rewards/config', json={'leaderboard_enabled': config_before['leaderboard_enabled']}, headers=admin_headers).status_code, 200)

        self.assertEqual(self.client.get('/api/admin/rewards/pending', headers=headers).status_code, 403)
        self.assertEqual(self.client.get('/api/admin/rewards/stats', headers=admin_headers).status_code, 200)

        config = self.client.get('/api/admin/rewards/config', headers=admin_headers).get_json()
        threshold_update = self.client.patch('/api/admin/rewards/config', json={
            'badges': {'civic_starter': 1},
            'leaderboard_enabled': config['leaderboard_enabled'],
        }, headers=admin_headers)
        self.assertEqual(threshold_update.status_code, 200)

    def test_09_review_correction_reverses_award_and_related_report_signal_is_admin_only(self):
        admin_headers = self.login_reward_admin()
        first_citizen = self.create_reward_citizen('First Related Reporter')
        second_citizen = self.create_reward_citizen('Second Related Reporter')
        shared_location = f'Community plaza {uuid.uuid4().hex[:8]}'
        first = self.client.post('/api/complaints', json={
            'title': 'Public plaza street light broken',
            'description': 'A street light near the plaza is broken and unsafe at night.',
            'category': 'Street Lighting',
            'location': shared_location,
        }, headers={'Authorization': f'Bearer {first_citizen["token"]}'}).get_json()['complaint']
        second = self.client.post('/api/complaints', json={
            'title': 'Public plaza street light broken',
            'description': 'Reporting the broken light at the plaza independently.',
            'category': 'Street Lighting',
            'location': shared_location,
        }, headers={'Authorization': f'Bearer {second_citizen["token"]}'}).get_json()['complaint']

        pending = self.client.get('/api/admin/rewards/pending', headers=admin_headers).get_json()['complaints']
        second_pending = next(item for item in pending if item['complaint_id'] == second['id'])
        self.assertIn(first['id'], second_pending['potential_related_reports'])

        decision_url = f'/api/admin/rewards/complaints/{first["id"]}/decision'
        self.assertEqual(self.client.post(decision_url, json={'eligible': True, 'reason': 'Verified field report.'}, headers=admin_headers).status_code, 200)
        self.assertEqual(self.client.post(decision_url, json={'eligible': False, 'reason': 'Correction: report later found invalid.'}, headers=admin_headers).status_code, 200)
        first_summary = self.client.get('/api/citizen/rewards', headers={'Authorization': f'Bearer {first_citizen["token"]}'}).get_json()
        self.assertEqual(first_summary['summary']['available_points'], 0)
        self.assertTrue(any(item['event_type'] == 'reversal' and item['points'] == -10 for item in first_summary['transactions']))


if __name__ == '__main__':
    unittest.main()
