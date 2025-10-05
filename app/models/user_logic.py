class user:
    def __init__(self, sex, height, age, weight, activity_level, planned_weekly_weight_loss=None,desired_weight=None):
        if sex not in ["male", "female"]:
            raise NameError("Sex must be 'male' or 'female'.")
        self.sex = sex
        
        self.height = height
        self.age = age  
        self.weight = weight
        self.planned_weekly_weight_loss = planned_weekly_weight_loss  # in kg/week
        
        valid_activity_levels = ["sedentary", "lightly active", "moderately active", "very active", "extra active"]
        if activity_level not in valid_activity_levels:
            raise NameError(f"Activity level must be one of: {', '.join(valid_activity_levels)}.")
        self.activity_level = activity_level

    def get_tdee(self):
        """Calculate Total Daily Energy Expenditure (TDEE)"""
        if self.sex == "male":
            base_bmr = 10 * self.weight + 6.25 * self.height - 5 * self.age + 5
        elif self.sex == "female":
            base_bmr = 10 * self.weight + 6.25 * self.height - 5 * self.age - 161
        
        activity_multipliers = {
            "sedentary": 1.2,
            "lightly active": 1.375,
            "moderately active": 1.55,
            "very active": 1.725,
            "extra active": 1.9
        }
        return base_bmr * activity_multipliers[self.activity_level]

    def get_planned_weekly_weight_loss(self):
        """Return planned weekly weight loss in kg (must be provided at initialization)"""
        if self.planned_weekly_weight_loss is None:
            raise ValueError("planned_weekly_weight_loss must be provided for weight loss calculations.")
        return self.planned_weekly_weight_loss

    def goal_based_bmr(self, goal):
        """Calculate calorie target based on goal"""
        tdee = self.get_tdee()

        valid_goals = ["Fat Loss", "General Health / Maintenance", "Build Muscle"]
        if goal not in valid_goals:
            raise NameError(f"Goal must be one of: {', '.join(valid_goals)}.")

        if goal == "Fat Loss":
            planned_weekly_loss = self.get_planned_weekly_weight_loss()
            # 7700 kcal ≈ 1 kg fat; divide by 7 for daily deficit
            daily_deficit = (planned_weekly_loss * 7700) / 7
            return tdee - daily_deficit
        elif goal == "General Health / Maintenance":
            return tdee
        elif goal == "Build Muscle":
            return tdee * 1.10

    def protein_intake(self, goal):
        """Calculate protein intake in grams"""
        valid_goals = ["Fat Loss", "General Health / Maintenance", "Build Muscle"]
        if goal not in valid_goals:
            raise NameError(f"Goal must be one of: {', '.join(valid_goals)}.")

        if goal == "Fat Loss":
            return 1.8 * self.weight
        elif goal == "General Health / Maintenance":
            return 2.0 * self.weight
        elif goal == "Build Muscle":
            return 2.2 * self.weight

    def fat_intake(self, goal):
        """Calculate fat intake in grams"""
        valid_goals = ["Fat Loss", "General Health / Maintenance", "Build Muscle"]
        if goal not in valid_goals:
            raise NameError(f"Goal must be one of: {', '.join(valid_goals)}.")
            
        total_goal_calories = self.goal_based_bmr(goal)
        
        fat_percentage = 0.30 if goal == "Build Muscle" else 0.25
        
        fat_calories = total_goal_calories * fat_percentage
        return fat_calories / 9

    def carbs_intake(self, goal):
        """Calculate carbohydrate intake in grams"""
        total_calories = self.goal_based_bmr(goal)
        
        protein_grams = self.protein_intake(goal)
        protein_calories = protein_grams * 4
        
        fat_grams = self.fat_intake(goal)
        fat_calories = fat_grams * 9
        
        remaining_calories = total_calories - protein_calories - fat_calories
        
        return max(0, remaining_calories / 4)  # avoid negative carbs