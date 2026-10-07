import random
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import User, AuditLog
from academics.models import SchoolYear, GradeLevel, Section, Subject, TeacherAssignment, GradingPeriod
from students.models import Student
from grades.models import Grade, GradeSubmission, GradeValidation, weighted_quarter_grade
from form137.models import Form137Record


class Command(BaseCommand):
    help = "Seed the database with comprehensive sample data for all roles and workflows."

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Delete existing non-admin users and sample data before seeding.',
        )
        parser.add_argument(
            '--fresh',
            action='store_true',
            help='Hard reset: delete ALL users (including admins) and every seeded '
                 'record, then re-seed from scratch. Existing passwords are destroyed.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        reset = options.get('reset', False)
        fresh = options.get('fresh', False)

        if fresh:
            self.stdout.write(self.style.WARNING('Hard reset: wiping ALL users and data...'))
            self._reset_sample_data(keep_admins=False)
        elif reset:
            self.stdout.write(self.style.WARNING('Resetting sample data...'))
            self._reset_sample_data(keep_admins=True)

        self.stdout.write(self.style.NOTICE('Seeding users...'))
        users = self._create_users()

        self.stdout.write(self.style.NOTICE('Seeding academic structure...'))
        school_years = self._create_school_years()
        grade_levels = self._create_grade_levels()
        sections = self._create_sections(school_years, grade_levels, users['teachers'])
        subjects = self._create_subjects(grade_levels)
        grading_periods = self._create_grading_periods(school_years)

        self.stdout.write(self.style.NOTICE('Seeding teacher assignments...'))
        assignments = self._create_teacher_assignments(users['teachers'], subjects, sections, school_years)

        self.stdout.write(self.style.NOTICE('Seeding students...'))
        students = self._create_students(grade_levels, sections, school_years, users['student_users'])

        self.stdout.write(self.style.NOTICE('Seeding grades and submissions...'))
        self._create_grades_and_submissions(students, assignments, grading_periods, school_years, sections, users)

        self.stdout.write(self.style.NOTICE('Seeding Form 137 records...'))
        self._create_form137_records(students, school_years, users['admin'])

        self.stdout.write(self.style.NOTICE('Seeding audit log samples...'))
        self._create_audit_logs(users)

        self.stdout.write(self.style.SUCCESS('Database seeded successfully.'))

    def _reset_sample_data(self, keep_admins=True):
        """Clear data that will be re-seeded. Optionally keep admin/superuser accounts."""
        GradeValidation.objects.all().delete()
        GradeSubmission.objects.all().delete()
        Grade.objects.all().delete()
        Form137Record.objects.all().delete()
        AuditLog.objects.all().delete()
        TeacherAssignment.objects.all().delete()
        GradingPeriod.objects.all().delete()
        Section.objects.all().delete()
        Subject.objects.all().delete()
        GradeLevel.objects.all().delete()
        SchoolYear.objects.all().delete()
        Student.objects.all().delete()

        if keep_admins:
            # Delete seeded sample users but preserve existing admins/superusers
            User.objects.filter(is_superuser=False, is_staff=False).delete()
        else:
            User.objects.all().delete()

    def _create_users(self):
        """Create sample users for every role."""
        users = {}

        # Admin
        admin, _ = User.objects.get_or_create(
            username='admin',
            defaults={
                'first_name': 'System',
                'last_name': 'Administrator',
                'email': 'admin@smis.edu',
                'role': 'admin',
                'is_staff': True,
                'is_superuser': True,
            }
        )
        admin.set_password('admin123')
        admin.save()
        users['admin'] = admin

        # Registrar
        registrar, _ = User.objects.get_or_create(
            username='registrar',
            defaults={
                'first_name': 'Maria',
                'last_name': 'Santos',
                'email': 'registrar@smis.edu',
                'role': 'registrar',
            }
        )
        registrar.set_password('registrar123')
        registrar.save()
        users['registrar'] = registrar

        # Teachers
        teacher_data = [
            ('reyes', 'Ana', 'Reyes'),
            ('lopez', 'Carmen', 'Lopez'),
            ('gonzaga', 'Jose', 'Gonzaga'),
            ('mendoza', 'Elena', 'Mendoza'),
            ('delacruz', 'Antonio', 'Delacruz'),
            ('bautista', 'Sophia', 'Bautista'),
        ]
        teachers = []
        for username, first, last in teacher_data:
            user, _ = User.objects.get_or_create(
                username=username,
                defaults={
                    'first_name': first,
                    'last_name': last,
                    'email': f'{username}@smis.edu',
                    'role': 'teacher',
                }
            )
            user.set_password('teacher123')
            user.save()
            teachers.append(user)
        users['teachers'] = teachers

        # Student users (will be linked to Student records)
        student_user_data = [
            ('student1', 'Luis', 'Castillo'),
            ('student2', 'Jennifer', 'Gonzales'),
            ('student3', 'Angela', 'Mendoza'),
            ('student4', 'Rose', 'Santos'),
            ('student5', 'Mark', 'Ramos'),
        ]
        student_users = []
        for username, first, last in student_user_data:
            user, _ = User.objects.get_or_create(
                username=username,
                defaults={
                    'first_name': first,
                    'last_name': last,
                    'email': f'{username}@smis.edu',
                    'role': 'student',
                }
            )
            user.set_password('student123')
            user.save()
            student_users.append(user)
        users['student_users'] = student_users

        return users

    def _create_school_years(self):
        """Create previous and current school years."""
        sy24_25, _ = SchoolYear.objects.get_or_create(
            name='2024-2025',
            defaults={'is_current': False}
        )
        sy25_26, _ = SchoolYear.objects.get_or_create(
            name='2025-2026',
            defaults={'is_current': True}
        )
        return {'2024-2025': sy24_25, '2025-2026': sy25_26}

    def _create_grade_levels(self):
        """Create Grade 7-12 levels."""
        grade_levels = {}
        for level in range(7, 13):
            gl, _ = GradeLevel.objects.get_or_create(
                level=level,
                defaults={'name': f'Grade {level}', 'description': f'Grade {level} level'}
            )
            grade_levels[level] = gl
        return grade_levels

    def _create_sections(self, school_years, grade_levels, teachers):
        """Create sections A/B/C for each grade level and school year."""
        sections = {}
        section_names = ['A', 'B', 'C']

        for sy_name, sy in school_years.items():
            sections[sy_name] = {}
            for level, gl in grade_levels.items():
                sections[sy_name][level] = []
                for idx, name in enumerate(section_names):
                    section, _ = Section.objects.get_or_create(
                        name=f'Grade {level}-{name}',
                        grade_level=gl,
                        school_year=sy,
                        defaults={
                            'adviser': random.choice(teachers) if teachers else None
                        }
                    )
                    sections[sy_name][level].append(section)

        return sections

    def _create_subjects(self, grade_levels):
        """Create canonical JHS subjects per grade level."""
        subject_codes = {
            'Filipino': 'FIL',
            'English': 'ENG',
            'Mathematics': 'MATH',
            'Science': 'SCI',
            'Araling Panlipunan': 'AP',
            'Edukasyon sa Pagpapakatao': 'EsP',
            'MAPEH': 'MAPEH',
            'Music': 'MUSIC',
            'Arts': 'ARTS',
            'Physical Education': 'PE',
            'Health': 'HEALTH',
            'Technology and Livelihood Education': 'TLE',
        }

        # Core subjects per grade level
        core_subjects = [
            'Filipino', 'English', 'Mathematics', 'Science',
            'Araling Panlipunan', 'Edukasyon sa Pagpapakatao',
            'MAPEH', 'Technology and Livelihood Education'
        ]

        subjects = {}
        for level, gl in grade_levels.items():
            subjects[level] = []
            for name in core_subjects:
                subj, _ = Subject.objects.get_or_create(
                    code=f'{subject_codes[name]}{level}',
                    defaults={
                        'name': name,
                        'description': f'{name} for Grade {level}',
                        'grade_level': gl,
                        'is_active': True,
                    }
                )
                subjects[level].append(subj)

        return subjects

    def _create_grading_periods(self, school_years):
        """Create Q1-Q4 grading periods for each school year with month coverage."""
        periods = {}
        period_names = {1: 'Quarter 1', 2: 'Quarter 2', 3: 'Quarter 3', 4: 'Quarter 4'}
        # Typical Philippine school-year quarter month ranges (August start).
        month_ranges = {1: (8, 10), 2: (11, 1), 3: (2, 4), 4: (5, 7)}

        for sy_name, sy in school_years.items():
            periods[sy_name] = {}
            for order in range(1, 5):
                is_current = (sy_name == '2025-2026' and order == 1)
                start_month, end_month = month_ranges[order]
                gp, _ = GradingPeriod.objects.get_or_create(
                    order=order,
                    school_year=sy,
                    defaults={
                        'name': period_names[order],
                        'start_month': start_month,
                        'end_month': end_month,
                        'is_current': is_current,
                        'is_submissions_open': is_current,
                    }
                )
                # Ensure current year Q1 is open, others closed by default
                gp.is_current = is_current
                gp.is_submissions_open = is_current
                if not gp.start_month:
                    gp.start_month = start_month
                    gp.end_month = end_month
                gp.save()
                periods[sy_name][order] = gp

        return periods

    def _create_teacher_assignments(self, teachers, subjects, sections, school_years):
        """Assign teachers to subjects/sections realistically."""
        assignments = []
        current_sy = school_years['2025-2026']

        # Distribute teachers across subjects/sections
        teacher_idx = 0
        for level in range(7, 13):
            for subject in subjects[level]:
                # Assign 2-3 sections per subject to spread workload
                for section in sections['2025-2026'][level][:2]:
                    teacher = teachers[teacher_idx % len(teachers)]
                    assignment, _ = TeacherAssignment.objects.get_or_create(
                        teacher=teacher,
                        subject=subject,
                        section=section,
                        school_year=current_sy,
                    )
                    assignments.append(assignment)
                    teacher_idx += 1

        return assignments

    def _create_students(self, grade_levels, sections, school_years, student_users):
        """Create students with mixed statuses and link some to user accounts."""
        first_names_m = ['Luis', 'Antonio', 'Mark', 'Jose', 'Carlos', 'Daniel', 'Miguel', 'Gabriel', 'Rafael', 'David']
        first_names_f = ['Jennifer', 'Angela', 'Rose', 'Maria', 'Sofia', 'Isabella', 'Emma', 'Lucia', 'Carmen', 'Linda']
        last_names = ['Castillo', 'Gonzales', 'Mendoza', 'Santos', 'Ramos', 'Reyes', 'Cruz', 'Garcia', 'Torres', 'Rivera',
                      'Flores', 'Dela Cruz', 'Bautista', 'Domingo', 'Villanueva', 'Santiago', 'Aquino', 'Navarro', 'Salazar', 'Lim']

        statuses = ['active'] * 8 + ['inactive'] + ['transferred'] + ['dropped']
        sexes = ['M', 'F']

        students = []
        student_idx = 1

        for level in range(7, 13):
            for section in sections['2025-2026'][level]:
                # 4-6 students per section
                for _ in range(random.randint(4, 6)):
                    sex = random.choice(sexes)
                    first = random.choice(first_names_m if sex == 'M' else first_names_f)
                    last = random.choice(last_names)
                    status = random.choice(statuses)

                    # Generate a 12-digit LRN: 2-digit region + 6-digit school + 4-digit student
                    lrn = f'12{202500:06d}{student_idx:04d}'

                    student, _ = Student.objects.get_or_create(
                        lrn=lrn,
                        defaults={
                            'first_name': first,
                            'last_name': last,
                            'middle_name': random.choice(['', 'A', 'B', 'C', 'D']),
                            'sex': sex,
                            'birthdate': date(2010 - (level - 7), random.randint(1, 12), random.randint(1, 28)),
                            'birthplace': f'{last} City, Philippines',
                            'address': f'{random.randint(1, 999)} {last} St., Paquito S. Yu Memorial NHS District',
                            'phone': f'09{random.randint(100000000, 999999999)}',
                            'email': f'{first.lower()}.{last.lower()}{student_idx}@student.smis.edu',
                            'parent_name': f'{random.choice(first_names_m if sex == "F" else first_names_f)} {last}',
                            'parent_phone': f'09{random.randint(100000000, 999999999)}',
                            'parent_address': f'{random.randint(1, 999)} {last} St.',
                            'grade_level': grade_levels[level],
                            'section': section,
                            'school_year': school_years['2025-2026'],
                            'status': status,
                        }
                    )
                    students.append(student)
                    student_idx += 1

        # Link first 5 students to student user accounts
        for idx, user in enumerate(student_users):
            if idx < len(students):
                student = students[idx]
                student.user_account = user
                student.first_name = user.first_name
                student.last_name = user.last_name
                student.email = user.email
                student.save()

        return students

    def _create_grades_and_submissions(self, students, assignments, grading_periods, school_years, sections, users):
        """Create grades for all quarters with realistic workflow statuses."""
        teachers = users['teachers']
        registrar = users['registrar']
        current_sy = school_years['2025-2026']

        # Build assignment lookup by section/subject
        assignment_map = {}
        for a in assignments:
            key = (a.section_id, a.subject_id)
            assignment_map[key] = a

        # For current school year, create grades for all quarters
        for student in students:
            if student.status != 'active':
                continue

            level = student.grade_level.level
            section = student.section

            for subject in self._get_subjects_for_level(level):
                assignment = assignment_map.get((section.id, subject.id))
                if not assignment:
                    continue

                teacher = assignment.teacher

                for order in range(1, 5):
                    gp = grading_periods['2025-2026'][order]

                    # Determine grade workflow status based on quarter
                    if order == 1:
                        # Q1: fully validated (closed workflow)
                        status = 'validated'
                    elif order == 2:
                        # Q2: mix of pending submissions and validated
                        status = random.choice(['validated', 'submitted'])
                    elif order == 3:
                        # Q3: some drafts, some submitted
                        status = random.choice(['draft', 'submitted', 'validated'])
                    else:
                        # Q4: mostly drafts
                        status = random.choice(['draft', 'draft', 'submitted'])

                    # Generate realistic component scores. Each category is the
                    # sum of its items; maxima are class-wide highest possible
                    # scores shared across students in the same section/subject
                    # quarter (simplified here as fixed per-category maxima).
                    ww_items, ww_max = self._random_components(5, 10, 20)
                    pt_items, pt_max = self._random_components(3, 20, 35)
                    as_items, as_max = self._random_components(3, 15, 30)

                    written = sum(ww_items)
                    performance = sum(pt_items)
                    assessment = sum(as_items)

                    # A few classes use non-default category weights (must sum
                    # to 100); most keep the DepEd default WW 20 / PT 50 / QA 30.
                    ww_w, pt_w, as_w = (Decimal('20'), Decimal('50'), Decimal('30'))
                    if random.random() < 0.2:
                        ww_w, pt_w, as_w = random.choice([
                            (Decimal('30'), Decimal('40'), Decimal('30')),
                            (Decimal('25'), Decimal('50'), Decimal('25')),
                        ])
                    quarter_grade = weighted_quarter_grade(
                        written, ww_max * 5,
                        performance, pt_max * 3,
                        assessment, as_max * 3,
                        ww_w, pt_w, as_w,
                    ).quantize(Decimal('0.01'))
                    remarks = 'Passed' if quarter_grade >= 75 else ('Incomplete' if quarter_grade >= 60 else 'Failed')

                    grade, _ = Grade.objects.update_or_create(
                        student=student,
                        subject=subject,
                        grading_period=gp,
                        school_year=current_sy,
                        defaults={
                            'section': section,
                            'written_work_1': ww_items[0],
                            'written_work_2': ww_items[1],
                            'written_work_3': ww_items[2],
                            'written_work_4': ww_items[3],
                            'written_work_5': ww_items[4],
                            'written_work_1_highest': ww_max,
                            'written_work_2_highest': ww_max,
                            'written_work_3_highest': ww_max,
                            'written_work_4_highest': ww_max,
                            'written_work_5_highest': ww_max,
                            'written_work': written,
                            'written_work_highest': ww_max * 5,
                            'performance_task_1': pt_items[0],
                            'performance_task_2': pt_items[1],
                            'performance_task_3': pt_items[2],
                            'performance_task_1_highest': pt_max,
                            'performance_task_2_highest': pt_max,
                            'performance_task_3_highest': pt_max,
                            'performance_task': performance,
                            'performance_task_highest': pt_max * 3,
                            'assessment_1': as_items[0],
                            'assessment_2': as_items[1],
                            'assessment_3': as_items[2],
                            'assessment_1_highest': as_max,
                            'assessment_2_highest': as_max,
                            'assessment_3_highest': as_max,
                            'assessment': assessment,
                            'assessment_highest': as_max * 3,
                            'written_work_weight': ww_w,
                            'performance_task_weight': pt_w,
                            'assessment_weight': as_w,
                            'quarter_grade': quarter_grade,
                            'final_grade': quarter_grade,
                            'remarks': remarks,
                            'status': status,
                            'encoded_by': teacher,
                            'updated_by': teacher,
                        }
                    )

                    # Create submission records for submitted/validated grades
                    if status in ['submitted', 'validated']:
                        submission, _ = GradeSubmission.objects.get_or_create(
                            teacher=teacher,
                            subject=subject,
                            section=section,
                            school_year=current_sy,
                            grading_period=gp,
                            defaults={
                                'status': 'pending' if status == 'submitted' else 'approved',
                                'remarks': '' if status == 'submitted' else 'Validated by registrar',
                            }
                        )

                        if status == 'validated' and submission.status == 'pending':
                            submission.status = 'approved'
                            submission.remarks = 'Validated by registrar'
                            submission.save()
                            GradeValidation.objects.get_or_create(
                                submission=submission,
                                defaults={
                                    'validated_by': registrar,
                                    'status': 'approved',
                                    'remarks': 'Validated by registrar',
                                }
                            )

        # Create previous-year validated grades for Form 137 history.
        # Every active student in Grade 8-12 gets one prior year of validated
        # grades so that multi-year Form 137 records are realistic.
        prev_sections = sections['2024-2025']
        for student in students:
            if student.status != 'active':
                continue
            level = student.grade_level.level
            if level == 7:
                continue  # No previous year for Grade 7

            prev_level = level - 1
            prev_sy = school_years['2024-2025']
            prev_section = prev_sections[prev_level][0] if prev_sections.get(prev_level) else student.section

            for subject in self._get_subjects_for_level(prev_level):
                for order in range(1, 5):
                    gp = grading_periods['2024-2025'][order]
                    ww_items, ww_max = self._random_components(5, 10, 20)
                    pt_items, pt_max = self._random_components(3, 20, 35)
                    as_items, as_max = self._random_components(3, 15, 30)
                    written = sum(ww_items)
                    performance = sum(pt_items)
                    assessment = sum(as_items)
                    quarter_grade = weighted_quarter_grade(
                        written, ww_max * 5,
                        performance, pt_max * 3,
                        assessment, as_max * 3,
                    ).quantize(Decimal('0.01'))
                    Grade.objects.get_or_create(
                        student=student,
                        subject=subject,
                        grading_period=gp,
                        school_year=prev_sy,
                        defaults={
                            'section': prev_section,
                            'written_work_1': ww_items[0],
                            'written_work_2': ww_items[1],
                            'written_work_3': ww_items[2],
                            'written_work_4': ww_items[3],
                            'written_work_5': ww_items[4],
                            'written_work_1_highest': ww_max,
                            'written_work_2_highest': ww_max,
                            'written_work_3_highest': ww_max,
                            'written_work_4_highest': ww_max,
                            'written_work_5_highest': ww_max,
                            'written_work': written,
                            'written_work_highest': ww_max * 5,
                            'performance_task_1': pt_items[0],
                            'performance_task_2': pt_items[1],
                            'performance_task_3': pt_items[2],
                            'performance_task_1_highest': pt_max,
                            'performance_task_2_highest': pt_max,
                            'performance_task_3_highest': pt_max,
                            'performance_task': performance,
                            'performance_task_highest': pt_max * 3,
                            'assessment_1': as_items[0],
                            'assessment_2': as_items[1],
                            'assessment_3': as_items[2],
                            'assessment_1_highest': as_max,
                            'assessment_2_highest': as_max,
                            'assessment_3_highest': as_max,
                            'assessment': assessment,
                            'assessment_highest': as_max * 3,
                            'quarter_grade': quarter_grade,
                            'final_grade': quarter_grade,
                            'remarks': 'Passed' if quarter_grade >= 75 else ('Incomplete' if quarter_grade >= 60 else 'Failed'),
                            'status': 'validated',
                            'encoded_by': random.choice(teachers),
                            'updated_by': random.choice(teachers),
                        }
                    )

    @staticmethod
    def _random_components(count, min_max, max_max):
        """Generate `count` whole-number component scores with a shared maximum.

        Returns (scores, per_item_highest). Raw item scores are integers only
        (no decimals) — each score is a random whole number between 60% and
        100% of the per-item maximum. Weights stay at the model defaults
        (WW 20 / PT 50 / QA 30) for seeded rows.
        """
        per_item_highest = random.randint(min_max, max_max)
        low = int(per_item_highest * 0.6)
        scores = [random.randint(low, per_item_highest) for _ in range(count)]
        return scores, per_item_highest

    def _get_subjects_for_level(self, level):
        """Helper to fetch subjects for a grade level."""
        from academics.models import Subject
        return list(Subject.objects.filter(grade_level__level=level))

    def _create_form137_records(self, students, school_years, admin_user):
        """Generate Form 137 records for students with validated grades."""
        current_sy = school_years['2025-2026']

        for student in students:
            if student.status != 'active':
                continue

            validated_grades = Grade.objects.filter(
                student=student,
                school_year=current_sy,
                status='validated'
            )

            if validated_grades.exists():
                grade_level = validated_grades.first().subject.grade_level
                Form137Record.objects.get_or_create(
                    student=student,
                    school_year=current_sy,
                    grade_level=grade_level,
                    defaults={'generated_by': admin_user}
                )

    def _create_audit_logs(self, users):
        """Seed a small sample of audit trail entries for realistic history."""
        admin = users['admin']
        registrar = users['registrar']
        teacher = users['teachers'][0] if users['teachers'] else admin
        student = Student.objects.first()

        samples = [
            (admin, 'create', 'SchoolYear', 'Seeded school year 2025-2026'),
            (admin, 'create', 'Subject', 'Seeded Grade 7 subjects'),
            (teacher, 'grade_encode', 'Grade', 'Encoded Quarter 1 grades for Grade 7-A Mathematics'),
            (teacher, 'grade_submit', 'GradeSubmission', 'Submitted Quarter 1 grades for validation'),
            (registrar, 'grade_validate', 'GradeSubmission', 'Validated Quarter 1 Mathematics submission'),
            (registrar, 'grade_return', 'GradeSubmission', 'Returned submission: missing performance task scores'),
            (registrar, 'form137_generate', 'Form137Record', 'Generated Form 137 record'),
            (admin, 'login', 'User', 'Admin logged in'),
        ]

        for user, action, model_name, description in samples:
            AuditLog.objects.get_or_create(
                user=user,
                action=action,
                model_name=model_name,
                description=description,
                defaults={
                    'object_id': str(student.id) if student and model_name in ('Grade', 'Form137Record') else '',
                    'ip_address': '127.0.0.1',
                }
            )
