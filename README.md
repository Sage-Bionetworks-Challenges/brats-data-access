# brats-data-access

This tool automates the process of granting access to BraTS data (from 2023
and beyond). It regularly checks a Google Sheet containing Google Form responses
for new entries.  For every new entry, this tool will verify:

* Is the given username in the form a real Synapse account?
* Did the user register for the challenge?

> [!NOTE]
> This tool replaces the previous [BraTs-Validate-Users](https://github.com/Sage-Bionetworks-Challenges/BraTs-Validate-Users) tool, which was
> dependent on using RStudio.