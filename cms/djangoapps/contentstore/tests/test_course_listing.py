"""
Unit tests for getting the list of courses for a user through iterating all courses and
by reversing group name formats.
"""
import random
import time

from django.contrib.auth.models import Group
from django.http import HttpRequest

from contentstore.views.course import _accessible_courses_list, _accessible_courses_list_from_groups
from contentstore.tests.utils import AjaxEnabledTestClient
from courseware.tests.factories import UserFactory
from student.roles import CourseInstructorRole, CourseStaffRole
from xmodule.modulestore import Location
from xmodule.modulestore.django import loc_mapper
from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase
from xmodule.modulestore.tests.factories import CourseFactory

GROUP_NAME_WITH_DOTS = u'group_name_with_dots'
GROUP_NAME_WITH_SLASHES = u'group_name_with_slashes'
GROUP_NAME_WITH_COURSE_NAME_ONLY = u'group_name_with_course_name_only'
MAX_COURSES = 1000
MAX_ACCESSIBLE_COURSES = 50


class TestCourseListing(ModuleStoreTestCase):
    """
    Unit tests for getting the list of courses for a logged in user
    """
    def setUp(self):
        """
        Add a user and a course
        """
        super(TestCourseListing, self).setUp()
        # create and log in a staff user.
        self.user = UserFactory(is_staff=True)  # pylint: disable=no-member
        self.request = HttpRequest()
        self.request.user = self.user
        self.client = AjaxEnabledTestClient()
        self.client.login(username=self.user.username, password='test')

    def _create_course_with_access_groups(self, course_location, group_name_format=GROUP_NAME_WITH_DOTS, user=None):
        """
        Create dummy course with 'CourseFactory' and role (instructor/staff) groups with provided group_name_format
        """
        course_locator = loc_mapper().translate_location(
            course_location.course_id, course_location, False, True
        )
        course = CourseFactory.create(
            org=course_location.org,
            number=course_location.course,
            display_name=course_location.name
        )

        for role in [CourseInstructorRole, CourseStaffRole]:
            # pylint: disable=protected-access
            groupnames = role(course_locator)._group_names
            if group_name_format == GROUP_NAME_WITH_COURSE_NAME_ONLY:
                # Create role (instructor/staff) groups with course_name only: 'instructor_run'
                group, _ = Group.objects.get_or_create(name=groupnames[2])
            elif group_name_format == GROUP_NAME_WITH_SLASHES:
                # Create role (instructor/staff) groups with format: 'instructor_edX/Course/Run'
                # Since "Group.objects.get_or_create(name=groupnames[1])" would have made group with lowercase name
                # so manually create group name of old type
                if role == CourseInstructorRole:
                    group, _ = Group.objects.get_or_create(name=u'{}_{}'.format('instructor', course_location.course_id))
                else:
                    group, _ = Group.objects.get_or_create(name=u'{}_{}'.format('staff', course_location.course_id))
            else:
                # Create role (instructor/staff) groups with format: 'instructor_edx.course.run'
                group, _ = Group.objects.get_or_create(name=groupnames[0])

            if user is not None:
                user.groups.add(group)
        return course

    def tearDown(self):
        """
        Reverse the setup
        """
        self.client.logout()
        ModuleStoreTestCase.tearDown(self)

    def test_get_course_list(self):
        """
        Test getting courses with new access group format e.g. 'instructor_edx.course.run'
        """
        course_location = Location(['i4x', 'Org1', 'Course1', 'course', 'Run1'])
        self._create_course_with_access_groups(course_location, GROUP_NAME_WITH_DOTS, self.user)

        # get courses through iterating all courses
        courses_list = _accessible_courses_list(self.request)
        self.assertEqual(len(courses_list), 1)

        # get courses by reversing group name formats
        success, courses_list_by_groups = _accessible_courses_list_from_groups(self.request)
        self.assertTrue(success)
        self.assertEqual(len(courses_list_by_groups), 1)
        # check both course lists have same courses
        self.assertEqual(courses_list, courses_list_by_groups)

    def test_get_course_list_with_old_group_formats(self):
        """
        Test getting all courses with old course role (instructor/staff) groups
        """
        # create a course with new groups name format e.g. 'instructor_edx.course.run'
        course_location = Location(['i4x', 'Org_1', 'Course_1', 'course', 'Run_1'])
        self._create_course_with_access_groups(course_location, GROUP_NAME_WITH_DOTS, self.user)

        # create a course with old groups name format e.g. 'instructor_edX/Course/Run'
        old_course_location = Location(['i4x', 'Org_2', 'Course_2', 'course', 'Run_2'])
        self._create_course_with_access_groups(old_course_location, GROUP_NAME_WITH_SLASHES, self.user)

        # get courses through iterating all courses
        courses_list = _accessible_courses_list(self.request)
        self.assertEqual(len(courses_list), 2)

        # get courses by reversing groups name
        success, courses_list_by_groups = _accessible_courses_list_from_groups(self.request)
        self.assertTrue(success)
        self.assertEqual(len(courses_list_by_groups), 2)

        # create a new course with older group name format (with dots in names) e.g. 'instructor_edX/Course.name/Run.1'
        old_course_location = Location(['i4x', 'Org.Foo.Bar', 'Course.number', 'course', 'Run.name'])
        self._create_course_with_access_groups(old_course_location, GROUP_NAME_WITH_SLASHES, self.user)
        # get courses through iterating all courses
        courses_list = _accessible_courses_list(self.request)
        self.assertEqual(len(courses_list), 3)
        # get courses by reversing group name formats
        success, courses_list_by_groups = _accessible_courses_list_from_groups(self.request)
        self.assertTrue(success)
        self.assertEqual(len(courses_list_by_groups), 3)

        # create a new course with older group name format e.g. 'instructor_Run'
        old_course_location = Location(['i4x', 'Org_3', 'Course_3', 'course', 'Run_3'])
        self._create_course_with_access_groups(old_course_location, GROUP_NAME_WITH_COURSE_NAME_ONLY, self.user)

        # get courses through iterating all courses
        courses_list = _accessible_courses_list(self.request)
        self.assertEqual(len(courses_list), 4)

        # get courses by reversing group name formats
        success, courses_list_by_groups = _accessible_courses_list_from_groups(self.request)
        # check that getting course with this older format of access group fails for this format
        self.assertFalse(success)
        self.assertEqual(courses_list_by_groups, [])

    def test_course_listing_performance(self):
        """
        Create large number of courses and give access of some of these courses to the user and
        compare the time to fetch accessible courses for the user through traversing all courses and
        reversing django groups
        """
        # create and log in a non-staff user
        self.user = UserFactory()
        self.request.user = self.user
        self.client.login(username=self.user.username, password='test')

        # create list of random course numbers which will be accessible to the user
        user_course_ids = random.sample(range(1, MAX_COURSES + 1), MAX_ACCESSIBLE_COURSES)

        # create courses and assign those to the user which have their number in user_course_ids
        for number in range(1, MAX_COURSES + 1):
            org = 'Org{0}'.format(number)
            course = 'Course{0}'.format(number)
            run = 'Run{0}'.format(number)
            course_location = Location(['i4x', org, course, 'course', run])
            if number in user_course_ids:
                self._create_course_with_access_groups(course_location, GROUP_NAME_WITH_DOTS, self.user)
            else:
                self._create_course_with_access_groups(course_location, GROUP_NAME_WITH_DOTS)

        # time the get courses by iterating through all courses
        start_time = time.time()
        courses_list = _accessible_courses_list(self.request)
        time_1 = time.time() - start_time
        self.assertEqual(len(courses_list), MAX_ACCESSIBLE_COURSES)
        print 'Time taken for getting courses through traversing all courses = {0}'.format(time_1)

        # time again the get courses by iterating through all courses
        start_time = time.time()
        courses_list = _accessible_courses_list(self.request)
        time_2 = time.time() - start_time
        self.assertEqual(len(courses_list), MAX_ACCESSIBLE_COURSES)
        print 'Time taken for getting courses through traversing all courses (second time) = {0}'.format(time_2)

        # time the get courses by reversing django groups
        start_time = time.time()
        success, courses_list = _accessible_courses_list_from_groups(self.request)
        time_3 = time.time() - start_time
        self.assertTrue(success)
        self.assertEqual(len(courses_list), MAX_ACCESSIBLE_COURSES)
        print 'Time taken for getting courses through django groups = {0}'.format(time_3)

        # time again the get courses by reversing django groups
        start_time = time.time()
        success, courses_list = _accessible_courses_list_from_groups(self.request)
        time_4 = time.time() - start_time
        self.assertTrue(success)
        self.assertEqual(len(courses_list), MAX_ACCESSIBLE_COURSES)
        print 'Time taken for getting courses through django groups (second time) = {0}'.format(time_4)

        # test that the time taken by getting courses through reversing django groups is lower then the time
        # taken by traversing through all courses (if accessible courses are relatively small)
        self.assertTrue(time_1 >= time_3)  # simple fetch time
        self.assertTrue(time_2 >= time_4)  # cache fetch time
