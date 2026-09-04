-- ============================================================
-- task01: 66 表 DDL 重建脚本
-- 来源: edu.sql (权威)
-- 生成时间: 2026-08-16
-- 注意: 27 张自建表不在本脚本范围内，不会被 DROP
-- ============================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- -------------------------------------------
-- dim_channel
DROP TABLE IF EXISTS dim_channel;
CREATE TABLE dim_channel (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    channel_category_code VARCHAR(64) NOT NULL,
    channel_category_name VARCHAR(64) NOT NULL,
    channel_code VARCHAR(64) NOT NULL,
    channel_name VARCHAR(64) NOT NULL,
    sort_no INT NOT NULL DEFAULT 0,
    yn TINYINT NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_dim_channel_code (channel_category_code, channel_code)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '机构招生渠道维表';

-- -------------------------------------------
-- dim_course_category
DROP TABLE IF EXISTS dim_course_category;
CREATE TABLE dim_course_category (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    parent_id BIGINT NULL,
    category_code VARCHAR(64) NOT NULL,
    category_name VARCHAR(128) NOT NULL,
    category_level TINYINT NOT NULL,
    sort_no INT NOT NULL DEFAULT 0,
    yn TINYINT NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_dim_course_category_code (category_code),
    CONSTRAINT fk_dim_course_category_parent FOREIGN KEY (
        parent_id
    ) REFERENCES dim_course_category (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '课程分类维表';

-- -------------------------------------------
-- dim_question_type
DROP TABLE IF EXISTS dim_question_type;
CREATE TABLE dim_question_type (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    type_code VARCHAR(64) NOT NULL,
    type_name VARCHAR(64) NOT NULL,
    objective_flag TINYINT NOT NULL DEFAULT 1 COMMENT '枚举：0,1',
    auto_marking_flag TINYINT NOT NULL DEFAULT 1 COMMENT '枚举：0,1',
    sort_no INT NOT NULL DEFAULT 0,
    yn TINYINT NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_dim_question_type_code (type_code)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '题型维表';

-- -------------------------------------------
-- dim_learner_identity
DROP TABLE IF EXISTS dim_learner_identity;
CREATE TABLE dim_learner_identity (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    identity_code VARCHAR(64) NOT NULL,
    identity_name VARCHAR(64) NOT NULL,
    sort_no INT NOT NULL DEFAULT 0,
    yn TINYINT NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_dim_learner_identity_code (identity_code)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '学习者身份维表';

-- -------------------------------------------
-- dim_grade
DROP TABLE IF EXISTS dim_grade;
CREATE TABLE dim_grade (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    parent_id BIGINT NULL,
    grade_code VARCHAR(64) NOT NULL,
    grade_name VARCHAR(64) NOT NULL,
    grade_type VARCHAR(16) NOT NULL COMMENT '枚举：stage,grade',
    sort_no INT NOT NULL DEFAULT 0,
    yn TINYINT NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_dim_grade_code (grade_code),
    CONSTRAINT fk_dim_grade_parent FOREIGN KEY (
        parent_id
    ) REFERENCES dim_grade (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '学业层级维表';

-- -------------------------------------------
-- dim_education_level
DROP TABLE IF EXISTS dim_education_level;
CREATE TABLE dim_education_level (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    level_code VARCHAR(64) NOT NULL,
    level_name VARCHAR(64) NOT NULL,
    sort_no INT NOT NULL DEFAULT 0,
    yn TINYINT NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_dim_education_level_code (level_code)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '学历层次维表';

-- -------------------------------------------
-- dim_learning_goal
DROP TABLE IF EXISTS dim_learning_goal;
CREATE TABLE dim_learning_goal (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    goal_code VARCHAR(64) NOT NULL,
    goal_name VARCHAR(64) NOT NULL,
    sort_no INT NOT NULL DEFAULT 0,
    yn TINYINT NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_dim_learning_goal_code (goal_code)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '学习目标维表';

-- -------------------------------------------
-- org_institution
DROP TABLE IF EXISTS org_institution;
CREATE TABLE org_institution (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    institution_code VARCHAR(64) NOT NULL,
    institution_name VARCHAR(128) NOT NULL,
    institution_type VARCHAR(32) NOT NULL COMMENT
    '枚举：training_center,school,education_brand,enterprise_academy',
    province VARCHAR(64) NULL,
    city VARCHAR(64) NULL,
    district VARCHAR(64) NULL,
    address VARCHAR(255) NULL,
    yn TINYINT NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_org_institution_code (institution_code)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '机构主表';

-- -------------------------------------------
-- org_campus
DROP TABLE IF EXISTS org_campus;
CREATE TABLE org_campus (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    institution_id BIGINT NOT NULL,
    campus_code VARCHAR(64) NOT NULL,
    campus_name VARCHAR(128) NOT NULL,
    province VARCHAR(64) NULL,
    city VARCHAR(64) NULL,
    district VARCHAR(64) NULL,
    address VARCHAR(255) NULL,
    yn TINYINT NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_org_campus_code (institution_id, campus_code),
    CONSTRAINT fk_org_campus_institution FOREIGN KEY (
        institution_id
    ) REFERENCES org_institution (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '校区表';

-- -------------------------------------------
-- org_department
DROP TABLE IF EXISTS org_department;
CREATE TABLE org_department (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    institution_id BIGINT NOT NULL,
    campus_id BIGINT NULL,
    parent_id BIGINT NULL,
    dept_code VARCHAR(64) NOT NULL,
    dept_name VARCHAR(128) NOT NULL,
    sort_no INT NOT NULL DEFAULT 0,
    yn TINYINT NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_org_department_code (institution_id, dept_code),
    CONSTRAINT fk_org_department_institution FOREIGN KEY (
        institution_id
    ) REFERENCES org_institution (id),
    CONSTRAINT fk_org_department_campus FOREIGN KEY (
        campus_id
    ) REFERENCES org_campus (id),
    CONSTRAINT fk_org_department_parent FOREIGN KEY (
        parent_id
    ) REFERENCES org_department (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '部门表';

-- -------------------------------------------
-- org_staff_role
DROP TABLE IF EXISTS org_staff_role;
CREATE TABLE org_staff_role (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    institution_id BIGINT NOT NULL,
    role_code VARCHAR(64) NOT NULL,
    role_name VARCHAR(64) NOT NULL,
    role_category VARCHAR(32) NOT NULL COMMENT
    '枚举：teacher,academic,sales,operations,service,management',
    sort_no INT NOT NULL DEFAULT 0,
    yn TINYINT NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_org_staff_role_code (institution_id, role_code),
    CONSTRAINT fk_org_staff_role_institution FOREIGN KEY (
        institution_id
    ) REFERENCES org_institution (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '机构职员角色表';

-- -------------------------------------------
-- org_institution_manager
DROP TABLE IF EXISTS org_institution_manager;
CREATE TABLE org_institution_manager (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    institution_id BIGINT NOT NULL,
    staff_id BIGINT NOT NULL,
    yn TINYINT NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_org_institution_manager_institution (institution_id),
    CONSTRAINT fk_org_institution_manager_institution FOREIGN KEY (
        institution_id
    ) REFERENCES org_institution (id),
    CONSTRAINT fk_org_institution_manager_staff FOREIGN KEY (
        staff_id
    ) REFERENCES staff_profile (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '机构负责人表';

-- -------------------------------------------
-- org_campus_manager
DROP TABLE IF EXISTS org_campus_manager;
CREATE TABLE org_campus_manager (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    campus_id BIGINT NOT NULL,
    staff_id BIGINT NOT NULL,
    yn TINYINT NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_org_campus_manager_campus (campus_id),
    CONSTRAINT fk_org_campus_manager_campus FOREIGN KEY (
        campus_id
    ) REFERENCES org_campus (id),
    CONSTRAINT fk_org_campus_manager_staff FOREIGN KEY (
        staff_id
    ) REFERENCES staff_profile (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '校区负责人表';

-- -------------------------------------------
-- org_department_manager
DROP TABLE IF EXISTS org_department_manager;
CREATE TABLE org_department_manager (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    department_id BIGINT NOT NULL,
    staff_id BIGINT NOT NULL,
    yn TINYINT NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_org_department_manager_department (department_id),
    CONSTRAINT fk_org_department_manager_department FOREIGN KEY (
        department_id
    ) REFERENCES org_department (id),
    CONSTRAINT fk_org_department_manager_staff FOREIGN KEY (
        staff_id
    ) REFERENCES staff_profile (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '部门负责人表';

-- -------------------------------------------
-- org_classroom
DROP TABLE IF EXISTS org_classroom;
CREATE TABLE org_classroom (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    institution_id BIGINT NOT NULL,
    campus_id BIGINT NULL,
    room_code VARCHAR(64) NOT NULL,
    room_name VARCHAR(128) NOT NULL,
    room_type VARCHAR(32) NOT NULL COMMENT '枚举：physical,live',
    max_capacity INT NULL,
    yn TINYINT NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_org_classroom_code (institution_id, room_code),
    CONSTRAINT fk_org_classroom_institution FOREIGN KEY (
        institution_id
    ) REFERENCES org_institution (id),
    CONSTRAINT fk_org_classroom_campus FOREIGN KEY (
        campus_id
    ) REFERENCES org_campus (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '教室资源表';

-- -------------------------------------------
-- sys_user
DROP TABLE IF EXISTS sys_user;
CREATE TABLE sys_user (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    nickname VARCHAR(64) NOT NULL,
    real_name VARCHAR(64) NULL,
    mobile VARCHAR(32) NULL,
    email VARCHAR(128) NULL,
    gender VARCHAR(16) NULL,
    avatar_url VARCHAR(255) NULL,
    birthday DATE NULL,
    yn TINYINT NOT NULL DEFAULT 1,
    last_login_at DATETIME NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_sys_user_mobile (mobile),
    UNIQUE KEY uk_sys_user_email (email)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '平台账号主表';

-- -------------------------------------------
-- staff_profile
DROP TABLE IF EXISTS staff_profile;
CREATE TABLE staff_profile (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    institution_id BIGINT NOT NULL,
    campus_id BIGINT NULL,
    dept_id BIGINT NULL,
    staff_no VARCHAR(64) NOT NULL,
    staff_role_id BIGINT NOT NULL,
    teacher_intro TEXT NULL,
    yn TINYINT NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_staff_profile_no (institution_id, staff_no),
    UNIQUE KEY uk_staff_profile_user (institution_id, user_id),
    CONSTRAINT fk_staff_profile_user FOREIGN KEY (
        user_id
    ) REFERENCES sys_user (id),
    CONSTRAINT fk_staff_profile_institution FOREIGN KEY (
        institution_id
    ) REFERENCES org_institution (id),
    CONSTRAINT fk_staff_profile_campus FOREIGN KEY (
        campus_id
    ) REFERENCES org_campus (id),
    CONSTRAINT fk_staff_profile_dept FOREIGN KEY (
        dept_id
    ) REFERENCES org_department (id),
    CONSTRAINT fk_staff_profile_role FOREIGN KEY (
        staff_role_id
    ) REFERENCES org_staff_role (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '职员档案表';

-- -------------------------------------------
-- student_profile
DROP TABLE IF EXISTS student_profile;
CREATE TABLE student_profile (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    learner_identity_id BIGINT NOT NULL,
    learning_goal_id BIGINT NOT NULL,
    education_level_id BIGINT NULL,
    grade_id BIGINT NULL,
    school_name VARCHAR(128) NULL,
    entrance_year INT NULL,
    industry_name VARCHAR(128) NULL,
    job_role_name VARCHAR(128) NULL,
    career_stage VARCHAR(64) NULL,
    years_of_experience INT NULL,
    profile_note TEXT NULL,
    yn TINYINT NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_student_profile_user (user_id),
    CONSTRAINT fk_student_profile_user FOREIGN KEY (
        user_id
    ) REFERENCES sys_user (id),
    CONSTRAINT fk_student_profile_identity FOREIGN KEY (
        learner_identity_id
    ) REFERENCES dim_learner_identity (id),
    CONSTRAINT fk_student_profile_goal FOREIGN KEY (
        learning_goal_id
    ) REFERENCES dim_learning_goal (id),
    CONSTRAINT fk_student_profile_education FOREIGN KEY (
        education_level_id
    ) REFERENCES dim_education_level (id),
    CONSTRAINT fk_student_profile_grade FOREIGN KEY (
        grade_id
    ) REFERENCES dim_grade (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '学员档案表';

-- -------------------------------------------
-- series
DROP TABLE IF EXISTS series;
CREATE TABLE series (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    institution_id BIGINT NOT NULL,
    delivery_mode VARCHAR(32) NOT NULL COMMENT
    '枚举：online_live,online_recorded,offline_face_to_face',
    series_code VARCHAR(64) NOT NULL,
    series_name VARCHAR(128) NOT NULL,
    `description` TEXT NULL,
    cover_url VARCHAR(255) NULL,
    target_learner_identity_codes JSON NULL,
    target_learning_goal_codes JSON NULL,
    target_grade_codes JSON NULL,
    sale_status VARCHAR(32) NOT NULL COMMENT '枚举：draft,on_sale,off_sale',
    created_by BIGINT NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_series_code (institution_id, series_code),
    CONSTRAINT fk_series_institution FOREIGN KEY (
        institution_id
    ) REFERENCES org_institution (id),
    CONSTRAINT fk_series_created_by FOREIGN KEY (
        created_by
    ) REFERENCES sys_user (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '课程系列主表';

-- -------------------------------------------
-- series_category_rel
DROP TABLE IF EXISTS series_category_rel;
CREATE TABLE series_category_rel (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    series_id BIGINT NOT NULL,
    category_id BIGINT NOT NULL,
    sort_no INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_series_category_rel (series_id, category_id),
    CONSTRAINT fk_series_category_rel_series FOREIGN KEY (
        series_id
    ) REFERENCES series (id),
    CONSTRAINT fk_series_category_rel_category FOREIGN KEY (
        category_id
    ) REFERENCES dim_course_category (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '课程系列分类关系表';

-- -------------------------------------------
-- series_cohort
DROP TABLE IF EXISTS series_cohort;
CREATE TABLE series_cohort (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    institution_id BIGINT NOT NULL,
    series_id BIGINT NOT NULL,
    campus_id BIGINT NULL,
    head_teacher_id BIGINT NOT NULL,
    cohort_code VARCHAR(64) NOT NULL,
    cohort_name VARCHAR(128) NOT NULL,
    sale_price DECIMAL(12, 2) NOT NULL COMMENT '班次售价',
    max_student_count INT NOT NULL,
    current_student_count INT NOT NULL DEFAULT 0,
    yn TINYINT NOT NULL DEFAULT 1,
    start_date DATE NOT NULL,
    end_date DATE NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_series_cohort_code (institution_id, cohort_code),
    CONSTRAINT fk_series_cohort_institution FOREIGN KEY (
        institution_id
    ) REFERENCES org_institution (id),
    CONSTRAINT fk_series_cohort_series FOREIGN KEY (
        series_id
    ) REFERENCES series (id),
    CONSTRAINT fk_series_cohort_campus FOREIGN KEY (
        campus_id
    ) REFERENCES org_campus (id),
    CONSTRAINT fk_series_cohort_teacher FOREIGN KEY (
        head_teacher_id
    ) REFERENCES staff_profile (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '班次主表';

-- -------------------------------------------
-- series_cohort_course
DROP TABLE IF EXISTS series_cohort_course;
CREATE TABLE series_cohort_course (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    cohort_id BIGINT NOT NULL,
    module_code VARCHAR(64) NOT NULL,
    module_name VARCHAR(128) NOT NULL,
    `description` TEXT NULL,
    lesson_count INT NOT NULL,
    total_hours DECIMAL(8, 2) NOT NULL,
    stage_no INT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_series_cohort_course_stage (cohort_id, stage_no),
    UNIQUE KEY uk_series_cohort_course_module (cohort_id, module_code),
    CONSTRAINT fk_series_cohort_course_cohort FOREIGN KEY (
        cohort_id
    ) REFERENCES series_cohort (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '班次课程模块表';

-- -------------------------------------------
-- series_cohort_session
DROP TABLE IF EXISTS series_cohort_session;
CREATE TABLE series_cohort_session (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    series_cohort_course_id BIGINT NOT NULL,
    room_id BIGINT NULL,
    session_no INT NOT NULL,
    session_title VARCHAR(128) NOT NULL,
    teaching_status VARCHAR(32) NOT NULL COMMENT
    '枚举：scheduled,in_progress,completed,cancelled',
    checkin_required TINYINT NOT NULL DEFAULT 0 COMMENT '枚举：0,1',
    teaching_date DATE NOT NULL,
    start_time TIME NULL,
    end_time TIME NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_series_cohort_session_no (
        series_cohort_course_id, session_no
    ),
    CONSTRAINT fk_series_cohort_session_course FOREIGN KEY (
        series_cohort_course_id
    ) REFERENCES series_cohort_course (id),
    CONSTRAINT fk_series_cohort_session_room FOREIGN KEY (
        room_id
    ) REFERENCES org_classroom (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '课次主表';

-- -------------------------------------------
-- session_teacher_rel
DROP TABLE IF EXISTS session_teacher_rel;
CREATE TABLE session_teacher_rel (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    session_id BIGINT NOT NULL,
    teacher_id BIGINT NOT NULL,
    sort_no INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_session_teacher_rel (session_id, teacher_id),
    CONSTRAINT fk_session_teacher_rel_session FOREIGN KEY (
        session_id
    ) REFERENCES series_cohort_session (id),
    CONSTRAINT fk_session_teacher_rel_teacher FOREIGN KEY (
        teacher_id
    ) REFERENCES staff_profile (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '课次教师关系表';

-- -------------------------------------------
-- session_asset
DROP TABLE IF EXISTS session_asset;
CREATE TABLE session_asset (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    session_id BIGINT NOT NULL,
    asset_code VARCHAR(64) NOT NULL,
    asset_name VARCHAR(128) NOT NULL,
    file_type VARCHAR(32) NOT NULL,
    material_category VARCHAR(32) NOT NULL COMMENT
    '枚举：video,handout,exercise,reference,image',
    sort_no INT NOT NULL DEFAULT 0,
    access_scope VARCHAR(32) NOT NULL COMMENT
    '枚举：public,trial,enrolled_only,internal_only',
    file_url VARCHAR(255) NOT NULL,
    file_size BIGINT NULL,
    uploader_user_id BIGINT NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_session_asset_code (session_id, asset_code),
    CONSTRAINT fk_session_asset_session FOREIGN KEY (
        session_id
    ) REFERENCES series_cohort_session (id),
    CONSTRAINT fk_session_asset_uploader FOREIGN KEY (
        uploader_user_id
    ) REFERENCES sys_user (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '课次资源表';

-- -------------------------------------------
-- session_video
DROP TABLE IF EXISTS session_video;
CREATE TABLE session_video (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    asset_id BIGINT NOT NULL,
    video_code VARCHAR(64) NOT NULL,
    video_title VARCHAR(128) NOT NULL,
    cover_url VARCHAR(255) NULL,
    duration_seconds INT NOT NULL,
    resolution_label VARCHAR(32) NULL,
    bitrate_kbps INT NOT NULL,
    transcode_status VARCHAR(32) NOT NULL COMMENT
    '枚举：pending,in_progress,completed,failed',
    review_status VARCHAR(32) NOT NULL COMMENT '枚举：pending,approved,rejected',
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_session_video_code (asset_id, video_code),
    CONSTRAINT fk_session_video_asset FOREIGN KEY (
        asset_id
    ) REFERENCES session_asset (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '课次视频表';

-- -------------------------------------------
-- session_video_chapter
DROP TABLE IF EXISTS session_video_chapter;
CREATE TABLE session_video_chapter (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    video_id BIGINT NOT NULL,
    chapter_no INT NOT NULL,
    chapter_title VARCHAR(128) NOT NULL,
    start_second INT NOT NULL,
    end_second INT NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_session_video_chapter_no (video_id, chapter_no),
    CONSTRAINT fk_session_video_chapter_video FOREIGN KEY (
        video_id
    ) REFERENCES session_video (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '课次视频章节表';

-- -------------------------------------------
-- session_homework
DROP TABLE IF EXISTS session_homework;
CREATE TABLE session_homework (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    session_id BIGINT NOT NULL,
    homework_code VARCHAR(64) NOT NULL,
    homework_name VARCHAR(128) NOT NULL,
    created_by BIGINT NOT NULL,
    due_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_session_homework_code (session_id, homework_code),
    CONSTRAINT fk_session_homework_session FOREIGN KEY (
        session_id
    ) REFERENCES series_cohort_session (id),
    CONSTRAINT fk_session_homework_created_by FOREIGN KEY (
        created_by
    ) REFERENCES staff_profile (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '课次作业表';

-- -------------------------------------------
-- session_exam
DROP TABLE IF EXISTS session_exam;
CREATE TABLE session_exam (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    session_id BIGINT NOT NULL,
    exam_code VARCHAR(64) NOT NULL,
    exam_name VARCHAR(128) NOT NULL,
    total_score DECIMAL(8, 2) NOT NULL,
    pass_score DECIMAL(8, 2) NOT NULL,
    publish_status VARCHAR(32) NOT NULL COMMENT '枚举：draft,published,closed',
    created_by BIGINT NOT NULL,
    duration_minutes INT NOT NULL,
    window_start_at DATETIME NOT NULL,
    deadline_at DATETIME NOT NULL,
    publish_at DATETIME NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_session_exam_code (session_id, exam_code),
    CONSTRAINT fk_session_exam_session FOREIGN KEY (
        session_id
    ) REFERENCES series_cohort_session (id),
    CONSTRAINT fk_session_exam_created_by FOREIGN KEY (
        created_by
    ) REFERENCES staff_profile (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '课次考试表';

-- -------------------------------------------
-- question_bank
DROP TABLE IF EXISTS question_bank;
CREATE TABLE question_bank (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    institution_id BIGINT NOT NULL,
    category_id BIGINT NOT NULL,
    bank_code VARCHAR(64) NOT NULL,
    bank_name VARCHAR(128) NOT NULL,
    yn TINYINT NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_question_bank_code (institution_id, bank_code),
    CONSTRAINT fk_question_bank_institution FOREIGN KEY (
        institution_id
    ) REFERENCES org_institution (id),
    CONSTRAINT fk_question_bank_category FOREIGN KEY (
        category_id
    ) REFERENCES dim_course_category (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '题库主表';

-- -------------------------------------------
-- question
DROP TABLE IF EXISTS `question`;
CREATE TABLE `question` (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    bank_id BIGINT NOT NULL,
    question_code VARCHAR(64) NOT NULL,
    question_type_id BIGINT NOT NULL,
    stem TEXT NOT NULL,
    options_json JSON NULL,
    answer_text TEXT NOT NULL,
    analysis_text TEXT NULL,
    yn TINYINT NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_question_code (bank_id, question_code),
    CONSTRAINT fk_question_bank FOREIGN KEY (
        bank_id
    ) REFERENCES question_bank (id),
    CONSTRAINT fk_question_type FOREIGN KEY (
        question_type_id
    ) REFERENCES dim_question_type (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '题目主表';

-- -------------------------------------------
-- session_homework_question_rel
DROP TABLE IF EXISTS session_homework_question_rel;
CREATE TABLE session_homework_question_rel (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    homework_id BIGINT NOT NULL,
    question_id BIGINT NOT NULL,
    sort_no INT NOT NULL,
    score DECIMAL(8, 2) NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_session_homework_question_rel (homework_id, question_id),
    UNIQUE KEY uk_session_homework_question_sort (homework_id, sort_no),
    CONSTRAINT fk_session_homework_question_rel_homework FOREIGN KEY (
        homework_id
    ) REFERENCES session_homework (id),
    CONSTRAINT fk_session_homework_question_rel_question FOREIGN KEY (
        question_id
    ) REFERENCES `question` (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '作业题目关系表';

-- -------------------------------------------
-- session_exam_question_rel
DROP TABLE IF EXISTS session_exam_question_rel;
CREATE TABLE session_exam_question_rel (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    exam_id BIGINT NOT NULL,
    question_id BIGINT NOT NULL,
    sort_no INT NOT NULL,
    score DECIMAL(8, 2) NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_session_exam_question_rel (exam_id, question_id),
    UNIQUE KEY uk_session_exam_question_sort (exam_id, sort_no),
    CONSTRAINT fk_session_exam_question_rel_exam FOREIGN KEY (
        exam_id
    ) REFERENCES session_exam (id),
    CONSTRAINT fk_session_exam_question_rel_question FOREIGN KEY (
        question_id
    ) REFERENCES `question` (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '考试题目关系表';

-- -------------------------------------------
-- coupon
DROP TABLE IF EXISTS coupon;
CREATE TABLE coupon (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    institution_id BIGINT NULL,
    issuer_scope VARCHAR(32) NOT NULL COMMENT '枚举：platform,institution',
    coupon_code VARCHAR(64) NOT NULL,
    coupon_name VARCHAR(128) NOT NULL,
    coupon_type VARCHAR(32) NOT NULL COMMENT '枚举：cash,discount,trial,gift',
    discount_amount DECIMAL(12, 2) NULL,
    discount_rate DECIMAL(8, 4) NULL,
    threshold_amount DECIMAL(12, 2) NOT NULL DEFAULT 0,
    total_count INT NOT NULL,
    per_user_limit INT NOT NULL DEFAULT 1,
    receive_count INT NOT NULL DEFAULT 0,
    used_count INT NOT NULL DEFAULT 0,
    yn TINYINT NOT NULL DEFAULT 1,
    valid_from DATETIME NOT NULL,
    valid_to DATETIME NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_coupon_code (coupon_code),
    CONSTRAINT fk_coupon_institution FOREIGN KEY (
        institution_id
    ) REFERENCES org_institution (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '优惠券主表';

-- -------------------------------------------
-- coupon_category_rel
DROP TABLE IF EXISTS coupon_category_rel;
CREATE TABLE coupon_category_rel (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    coupon_id BIGINT NOT NULL,
    category_id BIGINT NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_coupon_category_rel (coupon_id, category_id),
    CONSTRAINT fk_coupon_category_rel_coupon FOREIGN KEY (
        coupon_id
    ) REFERENCES coupon (id),
    CONSTRAINT fk_coupon_category_rel_category FOREIGN KEY (
        category_id
    ) REFERENCES dim_course_category (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '优惠券分类适用范围关系表';

-- -------------------------------------------
-- coupon_series_rel
DROP TABLE IF EXISTS coupon_series_rel;
CREATE TABLE coupon_series_rel (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    coupon_id BIGINT NOT NULL,
    series_id BIGINT NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_coupon_series_rel (coupon_id, series_id),
    CONSTRAINT fk_coupon_series_rel_coupon FOREIGN KEY (
        coupon_id
    ) REFERENCES coupon (id),
    CONSTRAINT fk_coupon_series_rel_series FOREIGN KEY (
        series_id
    ) REFERENCES series (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '优惠券课程系列适用范围关系表';

-- -------------------------------------------
-- series_exposure_log
DROP TABLE IF EXISTS series_exposure_log;
CREATE TABLE series_exposure_log (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    series_id BIGINT NOT NULL,
    exposure_scene VARCHAR(32) NOT NULL COMMENT
    '枚举：recommendation,search,activity,category,learning_center',
    position_no INT NOT NULL,
    device_type VARCHAR(32) NULL,
    exposed_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL,
    CONSTRAINT fk_series_exposure_log_user FOREIGN KEY (
        user_id
    ) REFERENCES sys_user (id),
    CONSTRAINT fk_series_exposure_log_series FOREIGN KEY (
        series_id
    ) REFERENCES series (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '课程系列曝光日志表';

-- -------------------------------------------
-- series_visit_log
DROP TABLE IF EXISTS series_visit_log;
CREATE TABLE series_visit_log (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    series_id BIGINT NOT NULL,
    ref_exposure_id BIGINT NULL,
    visit_source VARCHAR(32) NOT NULL COMMENT '枚举：recommendation,search_result,activity_page,favorite_list,shopping_cart,direct_access',
    stay_seconds INT NOT NULL DEFAULT 0,
    enter_at DATETIME NOT NULL,
    leave_at DATETIME NULL,
    created_at DATETIME NOT NULL,
    CONSTRAINT fk_series_visit_log_user FOREIGN KEY (
        user_id
    ) REFERENCES sys_user (id),
    CONSTRAINT fk_series_visit_log_series FOREIGN KEY (
        series_id
    ) REFERENCES series (id),
    CONSTRAINT fk_series_visit_log_exposure FOREIGN KEY (
        ref_exposure_id
    ) REFERENCES series_exposure_log (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '课程系列访问日志表';

-- -------------------------------------------
-- series_search_log
DROP TABLE IF EXISTS series_search_log;
CREATE TABLE series_search_log (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    keyword_text VARCHAR(255) NOT NULL,
    search_source VARCHAR(32) NOT NULL COMMENT
    '枚举：home_page,course_list_page,category_page,learning_center',
    result_count INT NOT NULL DEFAULT 0,
    clicked_series_id BIGINT NULL,
    searched_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL,
    CONSTRAINT fk_series_search_log_user FOREIGN KEY (
        user_id
    ) REFERENCES sys_user (id),
    CONSTRAINT fk_series_search_log_series FOREIGN KEY (
        clicked_series_id
    ) REFERENCES series (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '课程搜索日志表';

-- -------------------------------------------
-- series_favorite
DROP TABLE IF EXISTS series_favorite;
CREATE TABLE series_favorite (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    series_id BIGINT NOT NULL,
    favorite_source VARCHAR(32) NOT NULL COMMENT
    '枚举：series_detail,search_result,recommendation,activity_page',
    yn TINYINT NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_series_favorite (user_id, series_id),
    CONSTRAINT fk_series_favorite_user FOREIGN KEY (
        user_id
    ) REFERENCES sys_user (id),
    CONSTRAINT fk_series_favorite_series FOREIGN KEY (
        series_id
    ) REFERENCES series (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '课程系列收藏表';

-- -------------------------------------------
-- shopping_cart_item
DROP TABLE IF EXISTS shopping_cart_item;
CREATE TABLE shopping_cart_item (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    cohort_id BIGINT NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    cart_source VARCHAR(32) NOT NULL COMMENT
    '枚举：series_detail,search_result,recommendation,activity_page',
    added_at DATETIME NOT NULL,
    removed_at DATETIME NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_shopping_cart_item (user_id, cohort_id),
    CONSTRAINT fk_shopping_cart_item_user FOREIGN KEY (
        user_id
    ) REFERENCES sys_user (id),
    CONSTRAINT fk_shopping_cart_item_cohort FOREIGN KEY (
        cohort_id
    ) REFERENCES series_cohort (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '购物车明细表';

-- -------------------------------------------
-- consultation_record
DROP TABLE IF EXISTS consultation_record;
CREATE TABLE consultation_record (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    cohort_id BIGINT NOT NULL,
    consultant_user_id BIGINT NOT NULL,
    source_channel_id BIGINT NOT NULL,
    consult_channel VARCHAR(32) NOT NULL COMMENT
    '枚举：phone,online_chat,wechat,offline_visit',
    contact_mobile VARCHAR(32) NOT NULL,
    consult_content TEXT NULL,
    consulted_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    CONSTRAINT fk_consultation_user FOREIGN KEY (user_id) REFERENCES sys_user (
        id
    ),
    CONSTRAINT fk_consultation_cohort FOREIGN KEY (
        cohort_id
    ) REFERENCES series_cohort (id),
    CONSTRAINT fk_consultation_consultant FOREIGN KEY (
        consultant_user_id
    ) REFERENCES sys_user (id),
    CONSTRAINT fk_consultation_source_channel FOREIGN KEY (
        source_channel_id
    ) REFERENCES dim_channel (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '咨询记录表';

-- -------------------------------------------
-- coupon_receive_record
DROP TABLE IF EXISTS coupon_receive_record;
CREATE TABLE coupon_receive_record (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    coupon_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    receive_no VARCHAR(64) NOT NULL,
    receive_source VARCHAR(32) NOT NULL COMMENT '枚举：coupon_center,activity_page,series_detail,order_settlement,consultation',
    receive_status VARCHAR(32) NOT NULL COMMENT '枚举：unused,used,expired',
    yn TINYINT NOT NULL DEFAULT 1,
    received_at DATETIME NOT NULL,
    used_at DATETIME NULL,
    expired_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_coupon_receive_record_no (receive_no),
    KEY idx_coupon_receive_record_user_coupon (user_id, coupon_id),
    CONSTRAINT fk_coupon_receive_record_coupon FOREIGN KEY (
        coupon_id
    ) REFERENCES coupon (id),
    CONSTRAINT fk_coupon_receive_record_user FOREIGN KEY (
        user_id
    ) REFERENCES sys_user (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '领券记录表';

-- -------------------------------------------
-- order
DROP TABLE IF EXISTS `order`;
CREATE TABLE `order` (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    institution_id BIGINT NOT NULL,
    order_no VARCHAR(64) NOT NULL,
    user_id BIGINT NOT NULL,
    student_id BIGINT NOT NULL,
    coupon_receive_record_id BIGINT NULL,
    order_source_channel_id BIGINT NULL,
    order_status VARCHAR(32) NOT NULL COMMENT '枚举：pending,paid,completed,cancelled,partial_refunded,refunded',
    total_amount DECIMAL(12, 2) NOT NULL,
    discount_amount DECIMAL(12, 2) NOT NULL DEFAULT 0,
    payable_amount DECIMAL(12, 2) NOT NULL,
    paid_amount DECIMAL(12, 2) NULL,
    refund_amount DECIMAL(12, 2) NULL,
    remark TEXT NULL,
    paid_at DATETIME NULL,
    cancel_at DATETIME NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_order_no (institution_id, order_no),
    CONSTRAINT fk_order_institution FOREIGN KEY (
        institution_id
    ) REFERENCES org_institution (id),
    CONSTRAINT fk_order_user FOREIGN KEY (user_id) REFERENCES sys_user (id),
    CONSTRAINT fk_order_student FOREIGN KEY (
        student_id
    ) REFERENCES student_profile (id),
    CONSTRAINT fk_order_coupon_receive_record FOREIGN KEY (
        coupon_receive_record_id
    ) REFERENCES coupon_receive_record (id),
    CONSTRAINT fk_order_source_channel FOREIGN KEY (
        order_source_channel_id
    ) REFERENCES dim_channel (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '订单主表';

-- -------------------------------------------
-- order_item
DROP TABLE IF EXISTS order_item;
CREATE TABLE order_item (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    institution_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    student_id BIGINT NOT NULL,
    cohort_id BIGINT NOT NULL,
    order_item_status VARCHAR(32) NOT NULL COMMENT
    '枚举：pending,paid,completed,cancelled,refunded',
    item_name VARCHAR(255) NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    discount_amount DECIMAL(12, 2) NOT NULL DEFAULT 0,
    payable_amount DECIMAL(12, 2) NOT NULL,
    service_period_days INT NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    CONSTRAINT fk_order_item_institution FOREIGN KEY (
        institution_id
    ) REFERENCES org_institution (id),
    CONSTRAINT fk_order_item_order FOREIGN KEY (order_id) REFERENCES `order` (
        id
    ),
    CONSTRAINT fk_order_item_user FOREIGN KEY (user_id) REFERENCES sys_user (
        id
    ),
    CONSTRAINT fk_order_item_student FOREIGN KEY (
        student_id
    ) REFERENCES student_profile (id),
    CONSTRAINT fk_order_item_cohort FOREIGN KEY (
        cohort_id
    ) REFERENCES series_cohort (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '订单明细表';

-- -------------------------------------------
-- payment_record
DROP TABLE IF EXISTS payment_record;
CREATE TABLE payment_record (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    institution_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    payment_no VARCHAR(64) NOT NULL,
    payment_channel VARCHAR(32) NOT NULL COMMENT '枚举：wechat_pay,alipay,bank_card,offline_transfer,public_account,campus_cashier',
    payment_status VARCHAR(32) NOT NULL COMMENT
    '枚举：pending,paid,failed,closed,partial_refunded,refunded',
    amount DECIMAL(12, 2) NOT NULL,
    third_party_trade_no VARCHAR(128) NULL,
    refund_amount DECIMAL(12, 2) NULL,
    paid_at DATETIME NULL,
    refund_at DATETIME NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_payment_record_no (institution_id, payment_no),
    CONSTRAINT fk_payment_record_institution FOREIGN KEY (
        institution_id
    ) REFERENCES org_institution (id),
    CONSTRAINT fk_payment_record_order FOREIGN KEY (
        order_id
    ) REFERENCES `order` (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '支付记录表';

-- -------------------------------------------
-- refund_request
DROP TABLE IF EXISTS refund_request;
CREATE TABLE refund_request (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    institution_id BIGINT NOT NULL,
    refund_no VARCHAR(64) NOT NULL,
    order_id BIGINT NOT NULL,
    order_item_id BIGINT NOT NULL,
    payment_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    student_id BIGINT NOT NULL,
    refund_type VARCHAR(32) NOT NULL COMMENT '枚举：personal_reason,course_unsatisfied,schedule_conflict,duplicate_purchase',
    refund_reason TEXT NOT NULL,
    refund_status VARCHAR(32) NOT NULL COMMENT
    '枚举：pending,approved,rejected,refunded',
    apply_amount DECIMAL(12, 2) NOT NULL,
    approved_amount DECIMAL(12, 2) NULL,
    approver_user_id BIGINT NULL,
    remark TEXT NULL,
    yn TINYINT NOT NULL DEFAULT 1,
    applied_at DATETIME NOT NULL,
    approved_at DATETIME NULL,
    refunded_at DATETIME NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_refund_request_no (institution_id, refund_no),
    CONSTRAINT fk_refund_request_institution FOREIGN KEY (
        institution_id
    ) REFERENCES org_institution (id),
    CONSTRAINT fk_refund_request_order FOREIGN KEY (
        order_id
    ) REFERENCES `order` (id),
    CONSTRAINT fk_refund_request_order_item FOREIGN KEY (
        order_item_id
    ) REFERENCES order_item (id),
    CONSTRAINT fk_refund_request_payment FOREIGN KEY (
        payment_id
    ) REFERENCES payment_record (id),
    CONSTRAINT fk_refund_request_user FOREIGN KEY (
        user_id
    ) REFERENCES sys_user (id),
    CONSTRAINT fk_refund_request_student FOREIGN KEY (
        student_id
    ) REFERENCES student_profile (id),
    CONSTRAINT fk_refund_request_approver FOREIGN KEY (
        approver_user_id
    ) REFERENCES sys_user (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '退款申请表';

-- -------------------------------------------
-- student_cohort_rel
DROP TABLE IF EXISTS student_cohort_rel;
CREATE TABLE student_cohort_rel (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    institution_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    student_id BIGINT NOT NULL,
    cohort_id BIGINT NOT NULL,
    order_item_id BIGINT NOT NULL,
    enroll_status VARCHAR(32) NOT NULL COMMENT
    '枚举：active,completed,cancelled,refunded',
    enroll_at DATETIME NOT NULL,
    completed_at DATETIME NULL,
    cancelled_at DATETIME NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_student_cohort_rel_order_item (order_item_id),
    UNIQUE KEY uk_student_cohort_rel_student_cohort (student_id, cohort_id),
    CONSTRAINT fk_student_cohort_rel_institution FOREIGN KEY (
        institution_id
    ) REFERENCES org_institution (id),
    CONSTRAINT fk_student_cohort_rel_user FOREIGN KEY (
        user_id
    ) REFERENCES sys_user (id),
    CONSTRAINT fk_student_cohort_rel_student FOREIGN KEY (
        student_id
    ) REFERENCES student_profile (id),
    CONSTRAINT fk_student_cohort_rel_cohort FOREIGN KEY (
        cohort_id
    ) REFERENCES series_cohort (id),
    CONSTRAINT fk_student_cohort_rel_order_item FOREIGN KEY (
        order_item_id
    ) REFERENCES order_item (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '学员班次关系表';

-- -------------------------------------------
-- session_attendance
DROP TABLE IF EXISTS session_attendance;
CREATE TABLE session_attendance (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    institution_id BIGINT NOT NULL,
    session_id BIGINT NOT NULL,
    cohort_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    student_id BIGINT NOT NULL,
    attendance_status VARCHAR(32) NOT NULL COMMENT
    '枚举：pending,present,absent,leave,late',
    leave_type VARCHAR(32) NULL,
    remark TEXT NULL,
    checkin_time DATETIME NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_session_attendance (session_id, student_id),
    CONSTRAINT fk_session_attendance_institution FOREIGN KEY (
        institution_id
    ) REFERENCES org_institution (id),
    CONSTRAINT fk_session_attendance_session FOREIGN KEY (
        session_id
    ) REFERENCES series_cohort_session (id),
    CONSTRAINT fk_session_attendance_cohort FOREIGN KEY (
        cohort_id
    ) REFERENCES series_cohort (id),
    CONSTRAINT fk_session_attendance_user FOREIGN KEY (
        user_id
    ) REFERENCES sys_user (id),
    CONSTRAINT fk_session_attendance_student FOREIGN KEY (
        student_id
    ) REFERENCES student_profile (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '课次考勤表';

-- -------------------------------------------
-- session_video_play
DROP TABLE IF EXISTS session_video_play;
CREATE TABLE session_video_play (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    institution_id BIGINT NOT NULL,
    video_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    student_id BIGINT NOT NULL,
    play_session_no VARCHAR(64) NOT NULL,
    device_type VARCHAR(32) NOT NULL COMMENT '枚举：mobile,tablet,desktop',
    client_type VARCHAR(32) NOT NULL COMMENT '枚举：app,h5,pc_web,mini_program',
    device_os VARCHAR(32) NOT NULL COMMENT '枚举：ios,android,windows,macos,linux,harmonyos,unknown',
    last_position_seconds INT NOT NULL DEFAULT 0,
    progress_percent DECIMAL(5, 2) NOT NULL DEFAULT 0,
    completed_flag TINYINT NOT NULL DEFAULT 0 COMMENT '枚举：0,1',
    exit_reason VARCHAR(32) NULL,
    watched_seconds INT NOT NULL DEFAULT 0,
    started_at DATETIME NOT NULL,
    ended_at DATETIME NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_session_video_play_no (institution_id, play_session_no),
    CONSTRAINT fk_session_video_play_institution FOREIGN KEY (
        institution_id
    ) REFERENCES org_institution (id),
    CONSTRAINT fk_session_video_play_video FOREIGN KEY (
        video_id
    ) REFERENCES session_video (id),
    CONSTRAINT fk_session_video_play_user FOREIGN KEY (
        user_id
    ) REFERENCES sys_user (id),
    CONSTRAINT fk_session_video_play_student FOREIGN KEY (
        student_id
    ) REFERENCES student_profile (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '视频播放会话表';

-- -------------------------------------------
-- session_video_play_event
DROP TABLE IF EXISTS session_video_play_event;
CREATE TABLE session_video_play_event (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    play_session_id BIGINT NOT NULL,
    event_type VARCHAR(32) NOT NULL COMMENT '枚举：play,pause,resume,seek,complete,exit',
    position_seconds INT NOT NULL,
    playback_rate DECIMAL(4, 2) NOT NULL,
    network_type VARCHAR(32) NOT NULL COMMENT '枚举：wifi,mobile_5g,mobile_4g,mobile_3g,ethernet,offline,unknown',
    event_payload JSON NULL,
    event_time DATETIME NOT NULL,
    created_at DATETIME NOT NULL,
    CONSTRAINT fk_session_video_play_event_session FOREIGN KEY (
        play_session_id
    ) REFERENCES session_video_play (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '视频播放事件表';

-- -------------------------------------------
-- session_homework_submission
DROP TABLE IF EXISTS session_homework_submission;
CREATE TABLE session_homework_submission (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    institution_id BIGINT NOT NULL,
    homework_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    student_id BIGINT NOT NULL,
    session_id BIGINT NOT NULL,
    submit_no VARCHAR(64) NOT NULL,
    submit_status VARCHAR(32) NOT NULL COMMENT
    '枚举：submitted,expired_unsubmitted',
    total_score DECIMAL(8, 2) NULL,
    correction_status VARCHAR(32) NOT NULL COMMENT '枚举：pending,corrected',
    corrected_by BIGINT NULL,
    feedback_text TEXT NULL,
    submitted_at DATETIME NULL,
    corrected_at DATETIME NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_session_homework_submission_no (institution_id, submit_no),
    UNIQUE KEY uk_session_homework_submission_once (homework_id, student_id),
    CONSTRAINT fk_session_homework_submission_institution FOREIGN KEY (
        institution_id
    ) REFERENCES org_institution (id),
    CONSTRAINT fk_session_homework_submission_homework FOREIGN KEY (
        homework_id
    ) REFERENCES session_homework (id),
    CONSTRAINT fk_session_homework_submission_user FOREIGN KEY (
        user_id
    ) REFERENCES sys_user (id),
    CONSTRAINT fk_session_homework_submission_student FOREIGN KEY (
        student_id
    ) REFERENCES student_profile (id),
    CONSTRAINT fk_session_homework_submission_session FOREIGN KEY (
        session_id
    ) REFERENCES series_cohort_session (id),
    CONSTRAINT fk_session_homework_submission_teacher FOREIGN KEY (
        corrected_by
    ) REFERENCES staff_profile (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '作业提交表';

-- -------------------------------------------
-- session_exam_submission
DROP TABLE IF EXISTS session_exam_submission;
CREATE TABLE session_exam_submission (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    institution_id BIGINT NOT NULL,
    exam_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    student_id BIGINT NOT NULL,
    attempt_no VARCHAR(64) NOT NULL,
    attempt_status VARCHAR(32) NOT NULL COMMENT
    '枚举：not_started,in_progress,submitted,absent,timeout',
    duration_seconds INT NULL,
    score_value DECIMAL(8, 2) NULL,
    start_at DATETIME NULL,
    submit_at DATETIME NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_session_exam_submission_no (institution_id, attempt_no),
    UNIQUE KEY uk_session_exam_submission_once (exam_id, student_id),
    CONSTRAINT fk_session_exam_submission_institution FOREIGN KEY (
        institution_id
    ) REFERENCES org_institution (id),
    CONSTRAINT fk_session_exam_submission_exam FOREIGN KEY (
        exam_id
    ) REFERENCES session_exam (id),
    CONSTRAINT fk_session_exam_submission_user FOREIGN KEY (
        user_id
    ) REFERENCES sys_user (id),
    CONSTRAINT fk_session_exam_submission_student FOREIGN KEY (
        student_id
    ) REFERENCES student_profile (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '考试作答表';

-- -------------------------------------------
-- cohort_discussion_topic
DROP TABLE IF EXISTS cohort_discussion_topic;
CREATE TABLE cohort_discussion_topic (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    institution_id BIGINT NOT NULL,
    cohort_id BIGINT NOT NULL,
    creator_user_id BIGINT NOT NULL,
    topic_title VARCHAR(255) NOT NULL,
    content_text TEXT NOT NULL,
    is_pinned TINYINT NOT NULL DEFAULT 0 COMMENT '枚举：0,1',
    is_closed TINYINT NOT NULL DEFAULT 0 COMMENT '枚举：0,1',
    view_count INT NOT NULL DEFAULT 0,
    reply_count INT NOT NULL DEFAULT 0,
    last_reply_at DATETIME NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    CONSTRAINT fk_cohort_discussion_topic_institution FOREIGN KEY (
        institution_id
    ) REFERENCES org_institution (id),
    CONSTRAINT fk_cohort_discussion_topic_cohort FOREIGN KEY (
        cohort_id
    ) REFERENCES series_cohort (id),
    CONSTRAINT fk_cohort_discussion_topic_creator FOREIGN KEY (
        creator_user_id
    ) REFERENCES sys_user (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '班次讨论主题表';

-- -------------------------------------------
-- cohort_discussion_post
DROP TABLE IF EXISTS cohort_discussion_post;
CREATE TABLE cohort_discussion_post (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    institution_id BIGINT NOT NULL,
    topic_id BIGINT NOT NULL,
    parent_post_id BIGINT NULL,
    author_user_id BIGINT NOT NULL,
    content_text TEXT NOT NULL,
    like_count INT NOT NULL DEFAULT 0,
    reply_count INT NOT NULL DEFAULT 0,
    yn TINYINT NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    CONSTRAINT fk_cohort_discussion_post_institution FOREIGN KEY (
        institution_id
    ) REFERENCES org_institution (id),
    CONSTRAINT fk_cohort_discussion_post_topic FOREIGN KEY (
        topic_id
    ) REFERENCES cohort_discussion_topic (id),
    CONSTRAINT fk_cohort_discussion_post_parent FOREIGN KEY (
        parent_post_id
    ) REFERENCES cohort_discussion_post (id),
    CONSTRAINT fk_cohort_discussion_post_author FOREIGN KEY (
        author_user_id
    ) REFERENCES sys_user (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '班次讨论回复表';

-- -------------------------------------------
-- cohort_review
DROP TABLE IF EXISTS cohort_review;
CREATE TABLE cohort_review (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    institution_id BIGINT NOT NULL,
    cohort_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    student_id BIGINT NOT NULL,
    review_no VARCHAR(64) NOT NULL,
    score_overall TINYINT NOT NULL,
    score_teacher TINYINT NOT NULL,
    score_content TINYINT NOT NULL,
    score_service TINYINT NOT NULL,
    review_tags JSON NULL,
    review_content TEXT NULL,
    anonymous_flag TINYINT NOT NULL DEFAULT 0 COMMENT '枚举：0,1',
    yn TINYINT NOT NULL DEFAULT 1,
    reviewed_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_cohort_review_no (institution_id, review_no),
    UNIQUE KEY uk_cohort_review_once (cohort_id, student_id),
    CONSTRAINT fk_cohort_review_institution FOREIGN KEY (
        institution_id
    ) REFERENCES org_institution (id),
    CONSTRAINT fk_cohort_review_cohort FOREIGN KEY (
        cohort_id
    ) REFERENCES series_cohort (id),
    CONSTRAINT fk_cohort_review_user FOREIGN KEY (
        user_id
    ) REFERENCES sys_user (id),
    CONSTRAINT fk_cohort_review_student FOREIGN KEY (
        student_id
    ) REFERENCES student_profile (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '班次评价表';

-- -------------------------------------------
-- service_ticket
DROP TABLE IF EXISTS service_ticket;
CREATE TABLE service_ticket (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    institution_id BIGINT NOT NULL,
    ticket_no VARCHAR(64) NOT NULL,
    user_id BIGINT NOT NULL,
    student_id BIGINT NOT NULL,
    order_item_id BIGINT NOT NULL,
    refund_request_id BIGINT NULL,
    ticket_type VARCHAR(32) NOT NULL COMMENT '枚举：after_sales,complaint,refund',
    ticket_source VARCHAR(32) NOT NULL COMMENT '枚举：user_app,customer_service,system_auto,admin_manual',
    priority_level VARCHAR(32) NOT NULL COMMENT '枚举：low,medium,high,urgent',
    ticket_status VARCHAR(32) NOT NULL COMMENT '枚举：pending,in_progress,closed',
    assignee_user_id BIGINT NULL,
    title VARCHAR(255) NOT NULL,
    ticket_content TEXT NOT NULL,
    yn TINYINT NOT NULL DEFAULT 1,
    first_response_at DATETIME NULL,
    closed_at DATETIME NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_service_ticket_no (institution_id, ticket_no),
    CONSTRAINT fk_service_ticket_institution FOREIGN KEY (
        institution_id
    ) REFERENCES org_institution (id),
    CONSTRAINT fk_service_ticket_user FOREIGN KEY (
        user_id
    ) REFERENCES sys_user (id),
    CONSTRAINT fk_service_ticket_student FOREIGN KEY (
        student_id
    ) REFERENCES student_profile (id),
    CONSTRAINT fk_service_ticket_order_item FOREIGN KEY (
        order_item_id
    ) REFERENCES order_item (id),
    CONSTRAINT fk_service_ticket_refund_request FOREIGN KEY (
        refund_request_id
    ) REFERENCES refund_request (id),
    CONSTRAINT fk_service_ticket_assignee FOREIGN KEY (
        assignee_user_id
    ) REFERENCES sys_user (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '客服工单表';

-- -------------------------------------------
-- service_ticket_follow_record
DROP TABLE IF EXISTS service_ticket_follow_record;
CREATE TABLE service_ticket_follow_record (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    ticket_id BIGINT NOT NULL,
    follow_user_id BIGINT NOT NULL,
    follow_type VARCHAR(32) NOT NULL COMMENT '枚举：reply_user,status_update,refund_review,internal_note,escalation',
    follow_channel VARCHAR(32) NOT NULL COMMENT '枚举：phone,user_app,sms,wechat,internal_system,offline',
    follow_result VARCHAR(32) NOT NULL COMMENT '枚举：pending_follow_up,user_confirmed,user_unreachable,resolved,escalated',
    follow_content TEXT NOT NULL,
    followed_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    CONSTRAINT fk_service_ticket_follow_record_ticket FOREIGN KEY (
        ticket_id
    ) REFERENCES service_ticket (id),
    CONSTRAINT fk_service_ticket_follow_record_user FOREIGN KEY (
        follow_user_id
    ) REFERENCES sys_user (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '工单跟进记录表';

-- -------------------------------------------
-- service_ticket_satisfaction_survey
DROP TABLE IF EXISTS service_ticket_satisfaction_survey;
CREATE TABLE service_ticket_satisfaction_survey (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    survey_no VARCHAR(64) NOT NULL,
    user_id BIGINT NOT NULL,
    student_id BIGINT NOT NULL,
    ticket_id BIGINT NOT NULL,
    score_value TINYINT NULL,
    comment_text TEXT NULL,
    yn TINYINT NOT NULL DEFAULT 1,
    surveyed_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_service_ticket_satisfaction_survey_no (survey_no),
    UNIQUE KEY uk_service_ticket_satisfaction_survey_ticket (ticket_id),
    CONSTRAINT fk_service_ticket_satisfaction_survey_user FOREIGN KEY (
        user_id
    ) REFERENCES sys_user (id),
    CONSTRAINT fk_service_ticket_satisfaction_survey_student FOREIGN KEY (
        student_id
    ) REFERENCES student_profile (id),
    CONSTRAINT fk_service_ticket_satisfaction_survey_ticket FOREIGN KEY (
        ticket_id
    ) REFERENCES service_ticket (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '工单满意度调查表';

-- -------------------------------------------
-- teacher_compensation_bill
DROP TABLE IF EXISTS teacher_compensation_bill;
CREATE TABLE teacher_compensation_bill (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    institution_id BIGINT NOT NULL,
    bill_no VARCHAR(64) NOT NULL,
    teacher_id BIGINT NOT NULL,
    settle_period VARCHAR(32) NOT NULL,
    bill_status VARCHAR(32) NOT NULL COMMENT '枚举：pending,approved,paid',
    lesson_count INT NOT NULL,
    base_amount DECIMAL(12, 2) NOT NULL DEFAULT 0,
    bonus_amount DECIMAL(12, 2) NOT NULL DEFAULT 0,
    deduction_amount DECIMAL(12, 2) NOT NULL DEFAULT 0,
    payable_amount DECIMAL(12, 2) NOT NULL,
    approver_user_id BIGINT NULL,
    yn TINYINT NOT NULL DEFAULT 1,
    settled_at DATETIME NULL,
    paid_at DATETIME NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_teacher_compensation_bill_no (institution_id, bill_no),
    CONSTRAINT fk_teacher_compensation_bill_institution FOREIGN KEY (
        institution_id
    ) REFERENCES org_institution (id),
    CONSTRAINT fk_teacher_compensation_bill_teacher FOREIGN KEY (
        teacher_id
    ) REFERENCES staff_profile (id),
    CONSTRAINT fk_teacher_compensation_bill_approver FOREIGN KEY (
        approver_user_id
    ) REFERENCES sys_user (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '教师课酬账单表';

-- -------------------------------------------
-- teacher_compensation_item
DROP TABLE IF EXISTS teacher_compensation_item;
CREATE TABLE teacher_compensation_item (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    institution_id BIGINT NOT NULL,
    bill_id BIGINT NOT NULL,
    teacher_id BIGINT NOT NULL,
    cohort_id BIGINT NULL,
    session_id BIGINT NULL,
    item_type VARCHAR(32) NOT NULL COMMENT
    '枚举：session_fee,bonus,deduction,adjustment',
    unit_price DECIMAL(12, 2) NULL,
    item_amount DECIMAL(12, 2) NOT NULL,
    remark TEXT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_teacher_compensation_item_session_fee (bill_id, session_id),
    CONSTRAINT fk_teacher_compensation_item_institution FOREIGN KEY (
        institution_id
    ) REFERENCES org_institution (id),
    CONSTRAINT fk_teacher_compensation_item_bill FOREIGN KEY (
        bill_id
    ) REFERENCES teacher_compensation_bill (id),
    CONSTRAINT fk_teacher_compensation_item_teacher FOREIGN KEY (
        teacher_id
    ) REFERENCES staff_profile (id),
    CONSTRAINT fk_teacher_compensation_item_cohort FOREIGN KEY (
        cohort_id
    ) REFERENCES series_cohort (id),
    CONSTRAINT fk_teacher_compensation_item_session FOREIGN KEY (
        session_id
    ) REFERENCES series_cohort_session (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '教师课酬明细表';

-- -------------------------------------------
-- channel_commission_bill
DROP TABLE IF EXISTS channel_commission_bill;
CREATE TABLE channel_commission_bill (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    institution_id BIGINT NOT NULL,
    bill_no VARCHAR(64) NOT NULL,
    channel_id BIGINT NOT NULL,
    settle_period VARCHAR(32) NOT NULL,
    bill_status VARCHAR(32) NOT NULL COMMENT '枚举：pending,approved,paid',
    order_count INT NOT NULL,
    commission_amount DECIMAL(12, 2) NOT NULL,
    approver_user_id BIGINT NULL,
    yn TINYINT NOT NULL DEFAULT 1,
    settled_at DATETIME NULL,
    paid_at DATETIME NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_channel_commission_bill_no (institution_id, bill_no),
    CONSTRAINT fk_channel_commission_bill_institution FOREIGN KEY (
        institution_id
    ) REFERENCES org_institution (id),
    CONSTRAINT fk_channel_commission_bill_channel FOREIGN KEY (
        channel_id
    ) REFERENCES dim_channel (id),
    CONSTRAINT fk_channel_commission_bill_approver FOREIGN KEY (
        approver_user_id
    ) REFERENCES sys_user (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '渠道返佣账单表';

-- -------------------------------------------
-- channel_commission_item
DROP TABLE IF EXISTS channel_commission_item;
CREATE TABLE channel_commission_item (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    institution_id BIGINT NOT NULL,
    bill_id BIGINT NOT NULL,
    order_item_id BIGINT NOT NULL,
    commission_rate DECIMAL(8, 4) NOT NULL,
    base_amount DECIMAL(12, 2) NOT NULL,
    commission_amount DECIMAL(12, 2) NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_channel_commission_item_order_item (bill_id, order_item_id),
    CONSTRAINT fk_channel_commission_item_institution FOREIGN KEY (
        institution_id
    ) REFERENCES org_institution (id),
    CONSTRAINT fk_channel_commission_item_bill FOREIGN KEY (
        bill_id
    ) REFERENCES channel_commission_bill (id),
    CONSTRAINT fk_channel_commission_item_order_item FOREIGN KEY (
        order_item_id
    ) REFERENCES order_item (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '渠道返佣明细表';

-- -------------------------------------------
-- risk_alert_event
DROP TABLE IF EXISTS risk_alert_event;
CREATE TABLE risk_alert_event (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    institution_id BIGINT NOT NULL,
    alert_no VARCHAR(64) NOT NULL,
    alert_type VARCHAR(32) NOT NULL COMMENT '枚举：refund_anomaly,learning_anomaly,exam_anomaly,ugc_anomaly,operation_anomaly',
    risk_level VARCHAR(32) NOT NULL COMMENT '枚举：low,medium,high,critical',
    related_user_id BIGINT NULL,
    related_student_id BIGINT NULL,
    cohort_id BIGINT NULL,
    session_id BIGINT NULL,
    order_item_id BIGINT NULL,
    refund_request_id BIGINT NULL,
    related_exam_attempt_id BIGINT NULL,
    ugc_content_type VARCHAR(32) NULL COMMENT '枚举：topic,post,review',
    ugc_content_id BIGINT NULL,
    alert_source VARCHAR(32) NOT NULL COMMENT '枚举：rule_engine,manual_report,model_detection,scheduled_job',
    alert_reason TEXT NOT NULL,
    event_payload JSON NULL,
    alert_status VARCHAR(32) NOT NULL COMMENT '枚举：pending,in_progress,closed',
    yn TINYINT NOT NULL DEFAULT 1,
    detected_at DATETIME NOT NULL,
    closed_at DATETIME NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_risk_alert_event_no (institution_id, alert_no),
    CONSTRAINT fk_risk_alert_event_institution FOREIGN KEY (
        institution_id
    ) REFERENCES org_institution (id),
    CONSTRAINT fk_risk_alert_event_user FOREIGN KEY (
        related_user_id
    ) REFERENCES sys_user (id),
    CONSTRAINT fk_risk_alert_event_student FOREIGN KEY (
        related_student_id
    ) REFERENCES student_profile (id),
    CONSTRAINT fk_risk_alert_event_cohort FOREIGN KEY (
        cohort_id
    ) REFERENCES series_cohort (id),
    CONSTRAINT fk_risk_alert_event_session FOREIGN KEY (
        session_id
    ) REFERENCES series_cohort_session (id),
    CONSTRAINT fk_risk_alert_event_order_item FOREIGN KEY (
        order_item_id
    ) REFERENCES order_item (id),
    CONSTRAINT fk_risk_alert_event_refund_request FOREIGN KEY (
        refund_request_id
    ) REFERENCES refund_request (id),
    CONSTRAINT fk_risk_alert_event_exam_attempt FOREIGN KEY (
        related_exam_attempt_id
    ) REFERENCES session_exam_submission (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '风险预警事件表';

-- -------------------------------------------
-- risk_disposal_record
DROP TABLE IF EXISTS risk_disposal_record;
CREATE TABLE risk_disposal_record (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    alert_id BIGINT NOT NULL,
    handler_user_id BIGINT NOT NULL,
    action_type VARCHAR(32) NOT NULL COMMENT '枚举：review,contact_user,freeze_account,mark_false_positive,close_alert',
    action_result VARCHAR(32) NOT NULL COMMENT '枚举：pending_follow_up,confirmed_risk,false_positive,resolved',
    action_note TEXT NULL,
    handled_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    CONSTRAINT fk_risk_disposal_record_alert FOREIGN KEY (
        alert_id
    ) REFERENCES risk_alert_event (id),
    CONSTRAINT fk_risk_disposal_record_handler FOREIGN KEY (
        handler_user_id
    ) REFERENCES sys_user (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '风险处置记录表';

-- -------------------------------------------
-- ugc_moderation_task
DROP TABLE IF EXISTS ugc_moderation_task;
CREATE TABLE ugc_moderation_task (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    institution_id BIGINT NOT NULL,
    task_no VARCHAR(64) NOT NULL,
    content_type VARCHAR(32) NOT NULL COMMENT '枚举：topic,post,review',
    topic_id BIGINT NULL,
    post_id BIGINT NULL,
    review_id BIGINT NULL,
    submit_user_id BIGINT NOT NULL,
    moderator_user_id BIGINT NULL,
    moderation_status VARCHAR(32) NOT NULL COMMENT
    '枚举：pending,approved,rejected',
    risk_level VARCHAR(32) NOT NULL COMMENT '枚举：low,medium,high',
    reject_reason TEXT NULL,
    yn TINYINT NOT NULL DEFAULT 1,
    submitted_at DATETIME NOT NULL,
    moderated_at DATETIME NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_ugc_moderation_task_no (institution_id, task_no),
    CONSTRAINT fk_ugc_moderation_task_institution FOREIGN KEY (
        institution_id
    ) REFERENCES org_institution (id),
    CONSTRAINT fk_ugc_moderation_task_topic FOREIGN KEY (
        topic_id
    ) REFERENCES cohort_discussion_topic (id),
    CONSTRAINT fk_ugc_moderation_task_post FOREIGN KEY (
        post_id
    ) REFERENCES cohort_discussion_post (id),
    CONSTRAINT fk_ugc_moderation_task_review FOREIGN KEY (
        review_id
    ) REFERENCES cohort_review (id),
    CONSTRAINT fk_ugc_moderation_task_submit_user FOREIGN KEY (
        submit_user_id
    ) REFERENCES sys_user (id),
    CONSTRAINT fk_ugc_moderation_task_moderator FOREIGN KEY (
        moderator_user_id
    ) REFERENCES sys_user (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '内容审核任务表';

SET FOREIGN_KEY_CHECKS = 1;

-- 验证: SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='edu'; -- 应为 66 + 27 = 93