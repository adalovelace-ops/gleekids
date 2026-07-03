from django import forms
from .models import Applicant
from .validators import validate_applicant_upload

class ApplicantRegistrationForm(forms.ModelForm):
    confirm_password = forms.CharField(widget=forms.PasswordInput())
    UPPERCASE_FIELDS = [
        'first_name', 'middle_name', 'last_name', 'country', 'address',
        'city', 'state', 'zip_code', 'referral'
    ]

    class Meta:
        model = Applicant
        fields = [
            'first_name', 'middle_name', 'last_name', 'email', 'phone', 
            'country', 'date_of_birth', 'address', 'city', 'state', 
            'zip_code', 'referral', 'work_setup', 'password', 'resume', 'video',
            'video_2', 'tefl_certificate'
        ]

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        for field in self.UPPERCASE_FIELDS:
            value = cleaned_data.get(field)
            if isinstance(value, str):
                cleaned_data[field] = value.strip().upper()

        if password != confirm_password:
            raise forms.ValidationError("Passwords do not match")
        if password and len(password) < 8:
            raise forms.ValidationError("Password must be at least 8 characters.")
        if password and not any(char.isupper() for char in password):
            raise forms.ValidationError("Password must include at least one capital letter.")
        
        return cleaned_data

    def clean_resume(self):
        uploaded_file = self.cleaned_data.get('resume')
        validate_applicant_upload('resume', uploaded_file)
        return uploaded_file

    def clean_video(self):
        uploaded_file = self.cleaned_data.get('video')
        validate_applicant_upload('video', uploaded_file)
        return uploaded_file

    def clean_video_2(self):
        uploaded_file = self.cleaned_data.get('video_2')
        validate_applicant_upload('video_2', uploaded_file)
        return uploaded_file

    def clean_tefl_certificate(self):
        uploaded_file = self.cleaned_data.get('tefl_certificate')
        validate_applicant_upload('tefl_certificate', uploaded_file)
        return uploaded_file

    def save(self, commit=True):
        applicant = super().save(commit=False)
        applicant.set_password(self.cleaned_data['password'])
        if commit:
            applicant.save()
            self.save_m2m()
        return applicant
