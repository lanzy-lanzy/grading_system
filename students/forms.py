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
        for field_name, field in self.fields.items():
            if field_name != 'sex' and field_name != 'status':
                field.widget.attrs.update({
                    'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent dark:bg-gray-700 dark:text-white'
                })
            else:
                field.widget.attrs.update({
                    'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent dark:bg-gray-700 dark:text-white'
                })
