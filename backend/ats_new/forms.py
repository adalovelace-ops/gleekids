from django import forms
from .models import Applicant

class ApplicantRegistrationForm(forms.ModelForm):
    confirm_password = forms.CharField(widget=forms.PasswordInput())

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

        if password != confirm_password:
            raise forms.ValidationError("Passwords do not match")
        if password and len(password) < 8:
            raise forms.ValidationError("Password must be at least 8 characters.")
        if password and not any(char.isupper() for char in password):
            raise forms.ValidationError("Password must include at least one capital letter.")
        
        return cleaned_data
