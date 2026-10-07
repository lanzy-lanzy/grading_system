from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Count
from django.utils import timezone
from datetime import timedelta
from .models import Form137Record
from .utils import build_grade_blocks, build_printable_grade_blocks
from students.models import Student
from grades.models import Grade
from academics.models import SchoolYear, GradeLevel, GradingPeriod, Subject
from accounts.models import AuditLog
from accounts.decorators import role_required


def _form137_print_context(student, school_year, record):
    grade_blocks = build_grade_blocks(student)
    return {
        'student': student,
        'school_year': school_year,
        'record': record,
        'grade_blocks': grade_blocks,
        'print_blocks': build_printable_grade_blocks(grade_blocks),
    }


@role_required('admin', 'registrar')
def form137_list(request):
    school_years = SchoolYear.objects.all()
    grade_levels = GradeLevel.objects.all()
    
    sy_filter = request.GET.get('sy', '')
    gl_filter = request.GET.get('gl', '')
    query = request.GET.get('q', '')
    
    records = Form137Record.objects.select_related(
        'student', 'school_year', 'grade_level', 'generated_by'
    ).all()
    
    if sy_filter:
        records = records.filter(school_year_id=sy_filter)
    if gl_filter:
        records = records.filter(grade_level_id=gl_filter)
    if query:
        records = records.filter(
            Q(student__first_name__icontains=query) |
            Q(student__last_name__icontains=query) |
            Q(student__lrn__icontains=query)
        )
    
    # Stats
    all_records = Form137Record.objects.all()
    total_records = all_records.count()
    printed_count = all_records.filter(is_printed=True).count()
    unprinted_count = all_records.filter(is_printed=False).count()
    this_month_count = all_records.filter(
        date_generated__year=timezone.now().year,
        date_generated__month=timezone.now().month
    ).count()

    paginator = Paginator(records, 15)
    page = request.GET.get('page', 1)
    records_page = paginator.get_page(page)

    return render(request, 'form137/form137_list.html', {
        'records': records_page,
        'school_years': school_years,
        'grade_levels': grade_levels,
        'sy_filter': sy_filter,
        'gl_filter': gl_filter,
        'query': query,
        'total_records': total_records,
        'printed_count': printed_count,
        'unprinted_count': unprinted_count,
        'this_month_count': this_month_count,
    })


@role_required('admin', 'registrar')
def form137_generate(request, student_pk, sy_pk):
    student = get_object_or_404(Student, pk=student_pk)
    school_year = get_object_or_404(SchoolYear, pk=sy_pk)

    grade_blocks = build_grade_blocks(student)

    if not grade_blocks:
        messages.warning(request, 'No validated grades found for this student.')
        return redirect('form137:form137_list')

    # The record must reflect the grade level for the SELECTED school year.
    # build_grade_blocks sorts blocks ascending across ALL years, so taking
    # grade_blocks[0] would wrongly attach the student's earliest grade level
    # to the chosen year and create a mismatched (school_year, grade_level)
    # row that never reconciles with the correct one. Pick the block that
    # actually belongs to this school year; if the student has no validated
    # grades for it, there is nothing to generate.
    block_for_year = next(
        (b for b in grade_blocks if b['school_year'] == school_year), None
    )
    if block_for_year is None:
        messages.warning(
            request,
            f'No validated grades found for {student.full_name} in {school_year.name}.'
        )
        return redirect('form137:form137_list')

    grade_level = block_for_year['grade_level']

    record, created = Form137Record.objects.get_or_create(
        student=student,
        school_year=school_year,
        grade_level=grade_level,
        defaults={'generated_by': request.user}
    )

    if created:
        AuditLog.objects.create(
            user=request.user,
            action='form137_generate',
            model_name='Form137Record',
            object_id=str(record.id),
            description=f'Generated Form 137 for {student.full_name}'
        )

    return render(request, 'form137/form137_print.html', _form137_print_context(
        student,
        school_year,
        record,
    ))


@role_required('admin', 'registrar')
def form137_preview(request, record_pk):
    record = get_object_or_404(Form137Record, pk=record_pk)

    return render(request, 'form137/form137_print.html', _form137_print_context(
        record.student,
        record.school_year,
        record,
    ))


@role_required('admin', 'registrar')
@require_POST
def form137_mark_printed(request, record_pk):
    """Mark a Form 137 record as printed; called from the print view and record list."""
    record = get_object_or_404(Form137Record, pk=record_pk)

    was_printed = record.is_printed
    if not was_printed:
        record.is_printed = True
        record.save(update_fields=['is_printed'])
        AuditLog.objects.create(
            user=request.user,
            action='form137_print',
            model_name='Form137Record',
            object_id=str(record.id),
            description=f'Marked Form 137 as printed for {record.student.full_name} ({record.school_year})'
        )

    return JsonResponse({
        'status': 'ok',
        'record_id': record.id,
        'is_printed': record.is_printed,
        'newly_marked': not was_printed,
    })


@role_required('admin', 'registrar')
@transaction.atomic
def form137_bulk_generate(request):
    if request.method == 'POST':
        sy_pk = request.POST.get('school_year')
        if not sy_pk:
            messages.error(request, 'Please select a school year to generate.')
            return redirect('form137:form137_bulk_generate')
        school_year = get_object_or_404(SchoolYear, pk=sy_pk)

        students_with_grades = Student.objects.filter(
            grades__school_year=school_year,
            grades__status__in=['validated', 'locked']
        ).distinct().select_related('grade_level')

        created_count = 0
        existing_count = 0
        reconciled_count = 0

        for student in students_with_grades:
            # Determine the grade level from the student's validated grades for
            # THIS school year (deterministic ordering), falling back to the
            # enrolled grade level. Deriving it from an unscoped or arbitrarily
            # ordered grade caused mismatched (school_year, grade_level) rows.
            validated = Grade.objects.filter(
                student=student,
                school_year=school_year,
                status__in=['validated', 'locked'],
            ).select_related('subject__grade_level').order_by('subject__grade_level__level')

            first_grade = validated.first()
            grade_level = first_grade.subject.grade_level if first_grade else student.grade_level
            if grade_level is None:
                continue

            record, created = Form137Record.objects.get_or_create(
                student=student,
                school_year=school_year,
                grade_level=grade_level,
                defaults={'generated_by': request.user}
            )
            if created:
                created_count += 1
            else:
                existing_count += 1

            # Reconcile stale rows left by the previous bug: any unprinted
            # record for this student/year whose grade level no longer matches
            # the validated grades would otherwise sit in the list forever as
            # a "Pending" entry that can never be generated or matched.
            stale = Form137Record.objects.filter(
                student=student,
                school_year=school_year,
                is_printed=False,
            ).exclude(grade_level=grade_level)
            reconciled_count += stale.delete()[0]

        messages.success(
            request,
            f'Bulk generate for {school_year.name}: {created_count} created, '
            f'{existing_count} already existed'
            + (f', {reconciled_count} stale pending row(s) cleared.' if reconciled_count else '.')
        )
        return redirect('form137:form137_list')

    school_years = SchoolYear.objects.all()
    return render(request, 'form137/bulk_generate.html', {
        'school_years': school_years
    })


@role_required('admin', 'registrar')
def form137_export(request):
    import csv
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="form137_records_export.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Student Name', 'LRN', 'School Year', 'Grade Level', 'Generated By', 'Date Generated', 'Printed'])
    
    records = Form137Record.objects.select_related(
        'student', 'school_year', 'grade_level', 'generated_by'
    ).all()
    
    for record in records:
        writer.writerow([
            record.student.full_name,
            record.student.lrn,
            record.school_year.name,
            record.grade_level.name,
            record.generated_by.get_full_name() if record.generated_by else '',
            record.date_generated.strftime('%Y-%m-%d'),
            'Yes' if record.is_printed else 'No',
        ])
    
    return response
