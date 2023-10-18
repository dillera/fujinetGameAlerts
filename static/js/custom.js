

console.log

document.getElementById('whatsapp_number').addEventListener('blur', function() {
    var inputElement = document.getElementById('whatsapp_number');
    var phoneNumber = inputElement.value;

    if (phoneNumber) {
        var isValid = window.libphonenumber.isValidNumberForRegion(phoneNumber, 'US');
        if (!isValid) {
            alert('Invalid number. Please enter a valid international or US whats app number.');
            inputElement.value = '';
        }
    }
});


function validatePhoneNumber() {
    var inputElement = document.getElementById('phone_number');
    var phoneNumber = inputElement.value;

    if (phoneNumber) {
        var isValid = window.libphonenumber.isValidNumberForRegion(phoneNumber, 'US');
        if (!isValid) {
            alert('Invalid phone number. Please enter a valid US phone number for SMS or use Whats App.');
            inputElement.value = '';
        }
    }
}


function validateWhatsAppNumber() {
    var inputElement = document.getElementById('whatsapp_number');
    var phoneNumber = inputElement.value;

    if (phoneNumber) {
        var isValid = window.libphonenumber.isValidNumberForRegion(phoneNumber, 'UK');
        if (!isValid) {
            alert('Invalid number. Please enter a valid international or US whats app number.');
            inputElement.value = '';
        }
    }
}


function confirmDeletion() {
      return confirm('Are you sure you want to delete your info and all data?');
    }
