# -*- encoding: utf-8 -*-
"""Test class for CLI authentication

:Requirement: Auth

:CaseAutomation: Automated

:CaseLevel: Acceptance

:CaseComponent: CLI

:TestType: Functional

:CaseImportance: High

:Upstream: No
"""
from fauxfactory import gen_string
from robottelo import ssh
from robottelo.cli.auth import Auth
from robottelo.cli.base import CLIReturnCodeError
from robottelo.cli.factory import make_user
from robottelo.cli.org import Org
from robottelo.cli.settings import Settings
from robottelo.cli.user import User
from robottelo.config import settings
from robottelo.constants import HAMMER_CONFIG
from robottelo.decorators import (
    run_in_one_thread,
    skip_if_bug_open,
    tier1,
)
from robottelo.test import CLITestCase
from time import sleep

LOGEDIN_MSG = "Session exists, currently logged in as '{0}'"
LOGEDOFF_MSG = "Using sessions, you are currently not logged in"
NOTCONF_MSG = "Credentials are not configured."


def configure_sessions(enable=True, add_default_creds=False):
    """Enables the `use_sessions` option in hammer config"""
    result = ssh.command(
        '''sed -i -e '/username/d;/password/d;/use_sessions/d' {0};\
        echo '  :use_sessions: {1}' >> {0}'''.format(
            HAMMER_CONFIG,
            'true' if enable else 'false'
        )
    )
    if (result.return_code == 0 and add_default_creds):
        result = ssh.command(
            '''{{ echo '  :username: "{0}"';\
            echo '  :password: "{1}"'; }} >> {2}'''.format(
                settings.server.admin_username,
                settings.server.admin_password,
                HAMMER_CONFIG
                )
            )
    return result.return_code


@run_in_one_thread
class HammerAuthTestCase(CLITestCase):
    """Implements hammer authentication tests in CLI"""

    @classmethod
    def setUpClass(cls):
        """Creates users to be reused across tests"""
        super(HammerAuthTestCase, cls).setUpClass()
        cls.uname_admin = gen_string('alpha')
        cls.uname_viewer = gen_string('alpha')
        cls.password = gen_string('alpha')
        cls.mail = 'test@example.com'
        make_user({
                'login': cls.uname_admin,
                'password': cls.password,
                'admin': '1',
        })
        make_user({
                'login': cls.uname_viewer,
                'password': cls.password,
        })
        User.add_role({'login': cls.uname_viewer, 'role': 'Viewer'})

    @classmethod
    def tearDownClass(cls):
        """Making sure sessions are disabled after test run"""
        configure_sessions(False)

    @tier1
    def test_positive_create_session(self):
        """Check if user stays authenticated with session enabled

        :id: fcee7f5f-1040-41a9-bf17-6d0c24a93e22

        :Steps:

            1. Set use_sessions, set short expiration time
            2. Authenticate, assert credentials are not demanded
               on next command run
            3. Wait until session expires, assert credentials
               are required

        :expectedresults: The session is successfully created and
            expires after specified time
        """
        try:
            idle = Settings.list({'search': 'name=idle_timeout'})[0][u'value']
            Settings.set({'name': 'idle_timeout', 'value': 1})
            result = configure_sessions()
            self.assertEqual(result, 0, 'Failed to configure hammer sessions')
            Auth.login({
                'username': self.uname_admin,
                'password': self.password
            })
            result = Auth.status()
            self.assertIn(
                LOGEDIN_MSG.format(self.uname_admin),
                result[0][u'message']
            )
            # list organizations without supplying credentials
            with self.assertNotRaises(CLIReturnCodeError):
                Org.list(pass_credentials=False)
            # wait until session expires
            sleep(70)
            with self.assertRaises(CLIReturnCodeError):
                Org.list(pass_credentials=False)
            result = Auth.status()
            self.assertIn(
                LOGEDOFF_MSG.format(self.uname_admin),
                result[0][u'message']
            )
        finally:
            # reset timeout to default
            Settings.set({'name': 'idle_timeout', 'value': '{}'.format(idle)})

    @tier1
    def test_positive_disable_session(self):
        """Check if user logs out when session is disabled

        :id: 38ee0d85-c2fe-4cac-a992-c5dbcec11031

        :Steps:

            1. Set use_sessions
            2. Authenticate, assert credentials are not demanded
               on next command run
            3. Disable use_sessions

        :expectedresults: The session is terminated

        """
        result = configure_sessions()
        self.assertEqual(result, 0, 'Failed to configure hammer sessions')
        Auth.login({'username': self.uname_admin, 'password': self.password})
        result = Auth.status()
        self.assertIn(
            LOGEDIN_MSG.format(self.uname_admin),
            result[0][u'message']
        )
        # list organizations without supplying credentials
        with self.assertNotRaises(CLIReturnCodeError):
            Org.list(pass_credentials=False)

        # disabling sessions
        result = configure_sessions(False)
        self.assertEqual(result, 0, 'Failed to configure hammer sessions')
        result = Auth.status()
        self.assertIn(
            NOTCONF_MSG.format(self.uname_admin),
            result[0][u'message']
        )
        with self.assertRaises(CLIReturnCodeError):
            Org.list(pass_credentials=False)

    @tier1
    def test_positive_log_out_from_session(self):
        """Check if session is terminated when user logs out

        :id: 0ba05f2d-7b83-4b0c-a04c-80e62b7c4cf2

        :Steps:

            1. Set use_sessions
            2. Authenticate, assert credentials are not demanded
               on next command run
            3. Run `hammer auth logout`

        :expectedresults: The session is terminated

        """
        result = configure_sessions()
        self.assertEqual(result, 0, 'Failed to configure hammer sessions')
        Auth.login({'username': self.uname_admin, 'password': self.password})
        result = Auth.status()
        self.assertIn(
            LOGEDIN_MSG.format(self.uname_admin),
            result[0][u'message']
        )
        # list organizations without supplying credentials
        with self.assertNotRaises(CLIReturnCodeError):
            Org.list(pass_credentials=False)
        Auth.logout()
        result = Auth.status()
        self.assertIn(
            LOGEDOFF_MSG.format(self.uname_admin),
            result[0][u'message']
        )
        with self.assertRaises(CLIReturnCodeError):
            Org.list(pass_credentials=False)

    @tier1
    def test_positive_change_session(self):
        """Change from existing session to a different session

        :id: b6ea6f3c-fcbd-4e7b-97bd-f3e0e6b9da8f

        :Steps:

            1. Set use_sessions
            2. Authenticate, assert credentials are not demanded
               on next command run
            3. Login as a different user

        :expectedresults: The session is altered

        """
        result = configure_sessions()
        self.assertEqual(result, 0, 'Failed to configure hammer sessions')
        Auth.login({'username': self.uname_admin, 'password': self.password})
        result = Auth.status()
        self.assertIn(
            LOGEDIN_MSG.format(self.uname_admin),
            result[0][u'message']
        )
        # list organizations without supplying credentials
        with self.assertNotRaises(CLIReturnCodeError):
            Org.list(pass_credentials=False)
        Auth.login({'username': self.uname_viewer, 'password': self.password})
        result = Auth.status()
        self.assertIn(
            LOGEDIN_MSG.format(self.uname_viewer),
            result[0][u'message']
        )
        with self.assertNotRaises(CLIReturnCodeError):
            Org.list(pass_credentials=False)

    @tier1
    def test_positive_session_survives_unauthenticated_call(self):
        """Check if session stays up after unauthenticated call

        :id: 8bc304a0-70ea-489c-9c3f-ea8343c5284c

        :Steps:

            1. Set use_sessions
            2. Authenticate, assert credentials are not demanded
               on next command run
            3. Run `hammer ping`

        :expectedresults: The session is unchanged

        """
        result = configure_sessions()
        self.assertEqual(result, 0, 'Failed to configure hammer sessions')
        Auth.login({'username': self.uname_admin, 'password': self.password})
        result = Auth.status()
        self.assertIn(
            LOGEDIN_MSG.format(self.uname_admin),
            result[0][u'message']
        )
        # list organizations without supplying credentials
        with self.assertNotRaises(CLIReturnCodeError):
            Org.list(pass_credentials=False)
        ssh.command('hammer ping')
        result = Auth.status()
        self.assertIn(
            LOGEDIN_MSG.format(self.uname_admin),
            result[0][u'message']
        )
        with self.assertNotRaises(CLIReturnCodeError):
            Org.list(pass_credentials=False)

    @tier1
    @skip_if_bug_open("bugzilla", "1465552")
    def test_positive_session_survives_failed_login(self):
        """Check if session stays up after failed login attempt

        :id: 6c4d5c4c-eff0-411b-829f-0c2f2ec26132

        :BZ: 1465552

        :Steps:

            1. Set use_sessions
            2. Authenticate, assert credentials are not demanded
               on next command run
            3. Run login with invalid credentials

        :expectedresults: The session is unchanged

        """
        result = configure_sessions()
        self.assertEqual(result, 0, 'Failed to configure hammer sessions')
        Auth.login({'username': self.uname_admin, 'password': self.password})
        result = Auth.status()
        self.assertIn(
            LOGEDIN_MSG.format(self.uname_admin),
            result[0][u'message']
        )
        with self.assertNotRaises(CLIReturnCodeError):
            Org.list(pass_credentials=False)
        # using invalid password
        with self.assertRaises(CLIReturnCodeError):
            Auth.login({
                'username': self.uname_viewer,
                'password': gen_string('alpha')})
        # checking the session status again
        result = Auth.status()
        self.assertIn(
            LOGEDIN_MSG.format(self.uname_admin),
            result[0][u'message']
        )
        with self.assertNotRaises(CLIReturnCodeError):
            Org.list(pass_credentials=False)

    @skip_if_bug_open('bugzilla', '1471099')
    @tier1
    def test_positive_session_preceeds_saved_credentials(self):
        """Check if enabled session is mutually exclusive with
        saved credentials in hammer config

        :id: e4277298-1c24-494b-84a6-22f45f96e144

        :BZ: 1471099

        :Steps:

            1. Set use_sessions, set usernam and password,
               set short expiration time
            2. Authenticate, assert credentials are not demanded
               on next command run
            3. Wait until session expires

        :expectedresults: Session expires after specified time
            and saved credentials are not applied

        """
        try:
            idle = Settings.list({'search': 'name=idle_timeout'})[0][u'value']
            Settings.set({'name': 'idle_timeout', 'value': 1})
            result = configure_sessions(add_default_creds=True)
            self.assertEqual(result, 0, 'Failed to configure hammer sessions')
            Auth.login({
                'username': self.uname_admin,
                'password': self.password
            })
            result = Auth.status()
            self.assertIn(
                LOGEDIN_MSG.format(self.uname_admin),
                result[0][u'message']
            )
            # list organizations without supplying credentials
            with self.assertNotRaises(CLIReturnCodeError):
                Org.list(pass_credentials=False)
            # wait until session expires
            sleep(70)
            with self.assertRaises(CLIReturnCodeError):
                Org.list(pass_credentials=False)
            result = Auth.status()
            self.assertIn(
                LOGEDOFF_MSG.format(self.uname_admin),
                result[0][u'message']
            )
        finally:
            # reset timeout to default
            Settings.set({'name': 'idle_timeout', 'value': '{}'.format(idle)})

    @tier1
    def test_negative_no_credentials(self):
        """Attempt to execute command without authentication

        :id: 8a3b5c68-1027-450f-997c-c5630218f49f

        :expectedresults: Command is not executed
        """
        result = configure_sessions(False)
        self.assertEqual(result, 0, 'Failed to configure hammer sessions')
        result = Auth.status()
        self.assertIn(
            NOTCONF_MSG.format(self.uname_admin),
            result[0][u'message']
        )
        with self.assertRaises(CLIReturnCodeError):
            Org.list(pass_credentials=False)

    @tier1
    def test_negative_no_permissions(self):
        """Attempt to execute command out of user's permissions

        :id: 756f666f-270a-4b02-b587-a2ab09b7d46c

        :expectedresults: Command is not executed

        """
        result = configure_sessions()
        self.assertEqual(result, 0, 'Failed to configure hammer sessions')
        Auth.login({'username': self.uname_viewer, 'password': self.password})
        result = Auth.status()
        self.assertIn(
            LOGEDIN_MSG.format(self.uname_viewer),
            result[0][u'message']
        )
        # try to update user from viewer's session
        result = User.update({
            'login': self.uname_admin,
            'password': gen_string('alpha'),
        }, pass_credentials=False, return_raw_response=True)
        self.assertNotEqual(result.return_code, 0)