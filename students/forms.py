from django import forms
from accounts.models import User
from .models import Student


class StudentForm(forms.ModelForm):
    adviser = forms.ModelChoiceField(
        queryset=User.objects.filter(role='teacher', is_active=True).order_by('last_name', 'first_name'),
        required=True,
        empty_label='-- Select Adviser (Teacher) --',
        error_messages={'required': 'An adviser (teacher) must be assigned to the student.'},
        help_text='The selected teacher will see this student on their roster immediately.',
    )
    section = forms.ModelChoiceField(
        queryset=None,  # set in __init__ so the label/ordering stays consistent
        required=True,
        empty_label='-- Select Section --',
        error_messages={'required': 'A section is required so the student appears in the grade encoding roster.'},
        help_text='Pick a section the assigned teacher advises or teaches — the student '
                  'then shows up in that teacher\'s grade encoding grid right away.',
    )

    class Meta:
        model = Student
        fields = ('lrn', 'first_name', 'middle_name', 'last_name', 'suffix', 'sex', 
                  'birthdate', 'birthplace', 'address', 'phone', 'email',
                  'parent_name', 'parent_phone', 'parent_address',
                  'grade_level', 'section', 'school_year', 'adviser', 'status')
        widgets = {
            'birthdate': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from academics.models import Section

        self.fields['section'].queryset = Section.objects.select_related(
            'grade_level', 'school_year', 'adviser'
        ).order_by('grade_level__level', 'name')
        for field_name, field in self.fields.items():
            if field_name != 'sex' and field_name != 'status':
                field.widget.attrs.update({
                    'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent dark:bg-gray-700 dark:text-white'
                })
            else:
                field.widget.attrs.update({
                    'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent dark:bg-gray-700 dark:text-white'
                })

    def clean(self):
        """Keep the section/adviser pair consistent with grade encoding.

        A teacher's encoding grid is driven by their section enrolment, so the
        section chosen here decides whether the student is visible for grade
        entry at all. Requiring the adviser to actually own the class — either
        as its section adviser or as a teacher assigned to teach a subject in
        it — is what guarantees the student appears in their grid the moment the
        form is saved, instead of being enrolled in a class nobody can encode.
        The section's own adviser is never rewritten here: that is academic
        configuration and one enrolment must not reassign a whole class.
        """
        cleaned_data = super().clean()
        section = cleaned_data.get('section')
        adviser = cleaned_data.get('adviser')
        grade_level = cleaned_data.get('grade_level')

        if section and grade_level and section.grade_level != grade_level:
            self.add_error(
                'section',
                f'Section {section} does not belong to {grade_level}.'
            )

        if section and adviser:
            from academics.models import TeacherAssignment

            advises = section.adviser_id == adviser.pk
            teaches = TeacherAssignment.objects.filter(
                teacher=adviser, section=section
            ).exists()
            if not (advises or teaches):
                self.add_error(
                    'section',
                    f'{adviser.get_full_name()} neither advises {section} nor has a '
                    'subject assignment in it, so they could not encode grades for a '
                    'student placed here. Choose a section they advise or teach, or '
                    'pick one of their own advised sections.'
                )
        return cleaned_data
